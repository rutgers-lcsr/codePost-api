import time

from core.views.template import SuperUserListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers

from core.permissions.permissions import UserPermissions
from django.contrib.auth.models import User
from core.serializers.user import UserSerializer
from rest_framework.decorators import action

from core.permissions.helpers import returnNotAuthorized, returnForbidden

from rest_framework.authtoken.models import Token

from core.emails import USER_ACCESSIBLE_TEMPLATES
from core.emails import send_email_sendgrid, get_email_params, get_email_template_id
from core.permissions.helpers import isCourseMember, isCourseAdmin

from rest_framework import status

from core.models import Course, Assignment

class UserViewSet(SuperUserListProtectedViewSet):
  queryset = User.objects.all().order_by('-date_joined')
  serializer_class = UserSerializer
  permission_classes = (IsAuthenticated, UserPermissions)

  # Instead of id, index into /users/ detail routes with email
  lookup_field = 'email'
  lookup_value_regex = '[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

  @action(detail=True, methods=['POST'])
  def email(self, request, email=None):
    requestor = request.user
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
    if not (isCourseAdmin(requestor, course) and isCourseMember(user_to_email, course)):
        return returnForbidden()

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
    if template not in USER_ACCESSIBLE_TEMPLATES.keys():
        return Response({'error': "template is not valid"}, status=status.HTTP_400_BAD_REQUEST)

    # Are we running a test? If so, we'll send a dummy version of the email to the requestor
    testMode = not request.data.get('livemode', False)

    # Template specifies a function (callbefore) to run prior to sending an email.
    # If function returns True => send email
    # Else, don't
    template_obj = USER_ACCESSIBLE_TEMPLATES[template]
    if testMode or template_obj.get('callbefore', lambda x, y, z: False)(user_to_email, course, assignment):
        from_email = "team@codepost.io"
        to_email = requestor.email if testMode else user_to_email.email

        # if we're sending an email, we need to inject the right context variables.
        # some of these, we need from the user. these are passed in the request body.
        # some of these, we need to generate server-side. to generate these, we run
        # the generate_context function defined by the email template
        context = {
            'courseName': course.name,
            'coursePeriod': course.period,
            'assignmentName': assignment.name if assignment is not None else '',
            **template_obj.get('extra_parameters', {}),
        }

        if testMode:
            context = {
                **context,
                **template_obj.get('test_parameters', lambda x, y, z: {})(user_to_email, course, assignment),
            }
        else:
            context = {
                **context,
                **template_obj.get('generate_context', lambda x, y, z: {})(user_to_email, course, assignment),
            }

        sendgrid_template = template_obj.get('template')
        send_email_sendgrid(from_email, to_email, get_email_params(sendgrid_template, context),
                                                  get_email_template_id(sendgrid_template))

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

    serializer = UserSerializer(user)
    return Response(serializer.data)

  @action(detail=False, methods=['POST'])
  def requestAPIToken(self, request):
    user = request.user
    if not user.is_authenticated:
      return returnNotAuthorized()

    if not user.profile.canModifyRosters:
      return returnForbidden()

    if user.profile.api_token:
      user.profile.api_token.delete()

    token = Token.objects.create(user=user)
    user.profile.api_token = token
    user.save()

    serializer = UserSerializer(user, context={'request': request})
    return Response(serializer.data)
