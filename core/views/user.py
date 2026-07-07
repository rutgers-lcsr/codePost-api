# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import time

from core.views.auth import JWTSerializer
from core.views.template import SuperUserListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers

from core.permissions.permissions import UserPermissions
from core.models import User
from core.serializers.user import UserSerializer
from rest_framework.decorators import action

from core.permissions.helpers import returnNotAuthorized, returnForbidden

from rest_framework.authtoken.models import Token

from core.emails import USER_ACCESSIBLE_TEMPLATES, GraderReminderEmail, PublishNewAssignmentEmail, RegradesReminderEmail, UserAddedToCourseEmail
from core.permissions.helpers import isCourseMember
from core.permissions.capabilities import require_capability

from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework import filters

from django.db.models import Prefetch

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


  @action(detail=False, methods=['POST'])
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
    request.user = user  # hack to get JWTSerializer to work
    data = serializer.data 
    token = JWTSerializer.get_token(request.user)
    
    data['token'] = str(token)
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
    except Course.DoesNotExist:
        return returnForbidden()

    # bypass object-level permissions
    user_to_email = User.objects.get(email=email)

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
