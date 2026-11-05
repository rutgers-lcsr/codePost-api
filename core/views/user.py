# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import time

from core.views.auth import tokens_for_user
from core.views.template import SuperUserListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers

from core.permissions.permissions import UserPermissions
from core.permissions.template import SuperuserPermission
from core.models import User
from core.serializers.user import UserSerializer
from rest_framework.decorators import action

from core.permissions.helpers import returnNotAuthorized, returnForbidden, returnNotFound

from rest_framework.authtoken.models import Token

from core.emails import USER_ACCESSIBLE_TEMPLATES, GraderReminderEmail, PublishNewAssignmentEmail, RegradesReminderEmail, UserAddedToCourseEmail
from core.permissions.helpers import isCourseMember
from core.permissions.capabilities import require_capability

from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework import filters

from django.db.models import Prefetch, Q
from django.utils import timezone
from datetime import timedelta

from core.models import Course, Assignment

class UserPagination(PageNumberPagination):
  page_size = 50
  page_size_query_param = 'page_size'
  max_page_size = 100

class UserViewSet(SuperUserListProtectedViewSet):
  queryset = User.objects.select_related('profile').all().order_by('-date_joined')
  serializer_class = UserSerializer
  permission_classes = (IsAuthenticated, UserPermissions)
  pagination_class = UserPagination
  filter_backends = [filters.SearchFilter, filters.OrderingFilter]
  search_fields = ['email', 'first_name', 'last_name']
  ordering_fields = ['date_joined', 'email', 'last_login']

  # Instead of id, index into /users/ detail routes with email
  lookup_field = 'email'
  lookup_value_regex = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

  # Note: LightUserSerializer is available for future paginated endpoints
  # but list() uses full UserSerializer for backward compatibility with UsersTable

  # The staff console's People page filters the list by role and by idleness; the counts it shows
  # beside these filters come from /dashboard/stats/, so the definitions must match that view.
  ROLE_FILTERS = {
    'student': Q(student_courses__isnull=False),
    'grader': Q(grader_courses__isnull=False) | Q(superGrader_courses__isnull=False),
    'course_admin': Q(courseAdmin_courses__isnull=False),
    'platform_admin': Q(is_superuser=True),
  }

  def get_queryset(self):
    qs = super().get_queryset()
    if self.action != 'list':
      return qs
    role = self.request.query_params.get('role')
    if role:
      if role not in self.ROLE_FILTERS:
        raise ValidationError({'detail': f"role must be one of {', '.join(sorted(self.ROLE_FILTERS))}"})
      qs = qs.filter(self.ROLE_FILTERS[role]).distinct()
    if self.request.query_params.get('inactive') in ('1', 'true'):
      ninety_days_ago = timezone.now() - timedelta(days=90)
      qs = qs.filter(Q(last_login__isnull=True) | Q(last_login__lt=ninety_days_ago))
    return qs

  @extend_schema(parameters=[
    OpenApiParameter(name='role', required=False, type=str, enum=sorted(ROLE_FILTERS),
                     description='Only people holding this role in at least one course (platform_admin: superusers).'),
    OpenApiParameter(name='inactive', required=False, type=bool,
                     description='Only people who never signed in, or not in the last 90 days.'),
  ])
  def list(self, request, *args, **kwargs):
    return super().list(request, *args, **kwargs)


  # Superuser-only, enforced here: this mints tokens for an arbitrary user, and
  # UserPermissions alone never runs for a detail=False action with an invalid
  # body (TemplatePermission.has_permission falls through to True).
  @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated, SuperuserPermission])
  def user(self, request):
    """
    Given an email address as a query parameter, return the user object
    for that email address. This is a non-standard use of a GET request,
    but it is convenient for the client to be able to look up users by
    email address.
    """
    email = request.query_params.get('email', None)
    if email is None:
      return Response({'error': 'email query parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
      user = User.objects.get(email=email)
    except User.DoesNotExist:
      return Response({'error': 'user not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = UserSerializer(user, context={'request': request})
    request.user = user  # hack to get token issuance context to work
    data = serializer.data
    access, refresh = tokens_for_user(request.user)
    data['token'] = access
    data['refresh'] = refresh
    return Response(data)

  @action(detail=True, methods=['POST'])
  def email(self, request, email=None):
    requestor:User = request.user

    if not requestor.is_authenticated:
      return returnNotAuthorized()

    # User must specify a course in the request body. This course
    # represents the course the email pertains to. Note that a
    # user may belong to multiple courses in which the requestor
    # is an admin, so we need the requestor to specify which
    # course the email is coming from.
    courseID = request.data.get('course', None)
    try:
        course = Course.objects.get(id=courseID)
    except (Course.DoesNotExist, ValueError, TypeError):
        return returnForbidden()

    # bypass object-level permissions
    try:
        user_to_email = User.objects.get(email=email)
    except User.DoesNotExist:
        return returnNotFound("No user with that email address.")

    # does requestor have the authority to email this user?
    if not isCourseMember(user_to_email, course):
        return returnForbidden()
    require_capability(requestor, 'manage_roster', course)



    # grab the assignment specified in the request body, if one exists
    assignmentID = request.data.get('assignment', None)
    if assignmentID is None:
        assignment = None
    else:
        try:
            assignment = Assignment.objects.get(id=assignmentID)
        except Assignment.DoesNotExist:
            return returnForbidden()

        # Make sure the assignment belongs to the specified course
        if assignment.course.id != course.id:
            return returnForbidden()

    # Caller specifies a template via string. The template must be on a whitelist
    # of known templates
    template = request.data.get('template', None)
    if template not in USER_ACCESSIBLE_TEMPLATES:
        return Response({'error': "template is not valid"}, status=status.HTTP_400_BAD_REQUEST)

    # Are we running a test? If so, we'll send a dummy version of the email to the requestor
    testMode = not request.data.get('livemode', False)

    if testMode:
        # In test mode, we send the email to the requestor instead of the user
        user_to_email = requestor


    match template:
      # The add use case seems to be handled by the addToRoster endpoint.
      case 'add_student':
        UserAddedToCourseEmail(user_to_email).send_email(course.name, course.period, 'student')
      case 'add_grader':
        UserAddedToCourseEmail(user_to_email).send_email(course.name, course.period, 'grader')
      case 'add_admin':
        UserAddedToCourseEmail(user_to_email).send_email(course.name, course.period, 'admin')
      case 'publish_assignment':
        if not assignment:
          return returnForbidden()
        PublishNewAssignmentEmail(user_to_email).send_email(assignment=assignment)
      case 'grader_reminder':
        if not assignment:
          return returnForbidden()
        # is the user a grader for the course?
        if not course in user_to_email.grader_courses.all():
          return returnForbidden()
        GraderReminderEmail(user_to_email).send_email(assignment=assignment)
      case 'regrades_reminder':
        if not assignment:
          return returnForbidden()
        # is the user a grader for the course?
        if not course in user_to_email.grader_courses.all():
          return returnForbidden()
        RegradesReminderEmail(user_to_email).send_email(assignment=assignment)

    # wait (to avoid sending too many emails too quickly)
    time.sleep(0.300)

    return Response({'success': True})

  @action(detail=False, methods=['GET', 'PATCH'])
  def me(self, request):
    user = request.user
    if not user.is_authenticated:
      return returnNotAuthorized()

    if request.method == 'PATCH':
      if 'showProductTips' in request.data and isinstance(request.data['showProductTips'], bool):
        user.profile.showProductTips = request.data['showProductTips']
        user.save()
      else:
        raise serializers.ValidationError(
            "The only editable field is 'showProductTips'.")

    # Re-fetch the user with role memberships and each course's sub-relations prefetched.
    # UserSerializer renders CourseSerializer for all four role lists; without this every course
    # fans out into a per-course N+1 (capabilities/get_assignments role checks, studentCount,
    # sections, webhooks). With the role M2Ms cached, the `course in user.<role>_courses.all()`
    # checks inside compute_course_capabilities become in-memory lookups.
    prefetches = ['rubricEditor_courses', 'leader_sections']
    for rel in ('student_courses', 'grader_courses', 'superGrader_courses', 'courseAdmin_courses'):
      # select_related the org: compute_course_capabilities reads course.organization
      # (AI feature toggles) for every staff course.
      prefetches.append(Prefetch(rel, queryset=Course.objects.select_related('organization')))
      prefetches += [f'{rel}__assignments', f'{rel}__sections', f'{rel}__webhooks', f'{rel}__rubricEditors']
      prefetches.append(Prefetch(f'{rel}__students', queryset=User.objects.only('id')))

    user = User.objects.select_related('profile').prefetch_related(*prefetches).get(pk=user.pk)
    # Point request.user at the prefetched instance so the nested CourseSerializer capability/
    # rubric/assignment checks (which read request.user) hit the cached role M2Ms in memory.
    request.user = user

    serializer = UserSerializer(user, context={"request": request})

    return Response(serializer.data)

  @action(detail=False, methods=['POST'])
  def requestAPIToken(self, request):
    user = request.user
    if not user.is_authenticated:
      return returnNotAuthorized()

    if not user.profile.canModifyRosters:
      return returnForbidden()

    # Clean up any existing token rows for this user to avoid unique constraint
    # failures when profile.api_token is stale or unset.
    Token.objects.filter(user=user).delete()

    token = Token.objects.create(user=user)
    user.profile.api_token = token
    user.profile.save(update_fields=['api_token'])

    serializer = UserSerializer(user, context={'request': request})
    return Response(serializer.data)
