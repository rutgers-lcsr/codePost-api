import pytz

from rest_framework import serializers
from core.logging import logEvent
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Course, Organization, User
from core.serializers.assignment import AssignmentSerializer
from rest_framework.validators import UniqueTogetherValidator

from core.auth import Authentications, type_of_auth

from core.permissions.helpers import isCourseStaff
import logging

logger = logging.getLogger(__name__)

class CourseSerializer(ModelSerializerWithPOSTCheck):
  assignments = serializers.SerializerMethodField()
  studentCount = serializers.SerializerMethodField()

  class Meta:
    model = Course
    fields = ('id', 'name', 'period', 'assignments', 'sections', 'sendReleasedSubmissionsToBack',
              'showStudentsStatistics', 'timezone', 'emailNewUsers', 'anonymousGradingDefault', 'allowGradersToEditRubric', 
              'minComments', 'noUnfinalize', 'archived', 'lateDayCreditsAllowable', 'activateQueue', 'inviteCode', 'emailWhitelist', 
              'inviteCodeEnabled', 'enableStudentFeedbackNotifications', 'webhooks', 'expiration_date', 'organization', 'studentsCanSeeGraders', 'studentCount')
    read_only_fields = ('assignments', 'sections', 'inviteCode', 'webhooks', 'studentCount')
    extra_kwargs = {
        'organization': {'required': False}
    }
    validators = []

  def get_studentCount(self, obj):
    return obj.students.count()

  def validate_timezone(self, timezone):
    # Check that timezone corresponds to valid timezone
    options = pytz.all_timezones
    if timezone not in options:
      raise serializers.ValidationError("Timezone is not valid. See pytz.all_timezones for options.")
    return timezone

  def get_assignments(self, obj):
    
    if not self.context.get('request'):
      return []
    
    user = self.context.get('request').user

    if (user.is_active):
        if (isCourseStaff(user, obj)):
            return list(map(lambda x: x.id, obj.assignments.all()))
        else:
            # hide the IDs of invisible assignments from students. This way, a client can safely
            # load all the assignments in course.assignments without the risk of hitting a scary 403 error
            return list(map(lambda x: x.id, filter(lambda x: x.isVisible, obj.assignments.all())))
    else:
        return []

  def validate(self, data):
    # Add server-generated fields
    user = self.context['request'].user
    if user.is_superuser and 'organization' in data:
      # If superuser specifies an organization, let them use it
      # Verify it exists or is a valid instance (if serializer passed ID, it might be resolved already if ModelSerializer)
      # But since 'organization' might not be in the input fields of the serializer (it wasn't in Meta fields explicitly before I check),
      # I need to ensure it is writable.
      pass 
    else:
      # Default behavior for non-superusers or if org not specified
      organization = user.profile.organization
      data['organization'] = organization
      
    newData = super().validate(data)
    newFields = self.genProposedFields(newData)

    # Manually establish unique_together(name, organization, period) constraint. Django provides an error messages
    # in UniqueTogetherValidator but only seems to apply to fields of 2. With 3 fields in unique_together it
    # provides a 500 error
    organization = newFields['organization'] # Get the final organization
    others = Course.objects.filter(name=newFields['name'], period=newFields['period'], organization=organization)
    if (self.instance and len(others) > 1) or (not self.instance and len(others) > 0):  # don't count this course!
      raise serializers.ValidationError("A course with this name and period already exists in your organization.")

    return newData

  def create(self, validated_data):
    from core.views.course import generate_invite_code

    courseAdmin: User = self.context['request'].user
    obj: Course = super().create(validated_data)

    token = str(self.context['request'].auth)
    auth_type = type_of_auth(token)
  
    logEvent("Course Created",
             message=f"Course {obj.name} created by {courseAdmin.email} with auth type {auth_type}")


    # Make requesting user a courseAdmin of the course
    obj.courseAdmins.add(courseAdmin)

    # Make requesting user a grader of the course
    obj.graders.add(courseAdmin)

    # Create inaugural invite code. We create this code here because our database can't handle
    # default values produced by a function.
    obj.inviteCode = generate_invite_code()

    # save changes we made
    obj.save()

    return obj


class CourseSettingsSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = Course
    fields = ('id', 'sendReleasedSubmissionsToBack', 'showStudentsStatistics', 'timezone',
              'emailNewUsers', 'anonymousGradingDefault', 'allowGradersToEditRubric', 'archived', 'lateDayCreditsAllowable')


class CourseAISettingsSerializer(serializers.ModelSerializer):
  """Serializer for course AI configuration. Admin-only access."""
  ai_enabled = serializers.SerializerMethodField()
  
  class Meta:
    model = Course
    fields = ('id', 'ai_provider', 'ai_api_key', 'ai_base_url', 'ai_model', 'ai_enabled')
    extra_kwargs = {
      'ai_api_key': {'write_only': True}  # Never return API key in response
    }
  
  def get_ai_enabled(self, obj):
    """Returns True if AI is configured for this course."""
    return bool(obj.ai_provider and obj.ai_api_key)


class CourseRosterSerializer(ModelSerializerWithPOSTCheck):
  students = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  graders = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  superGraders = serializers.SlugRelatedField(
      many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  courseAdmins = serializers.SlugRelatedField(
      many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  inactive_students = serializers.SlugRelatedField(
      many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  inactive_graders = serializers.SlugRelatedField(
      many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  inactive_courseAdmins = serializers.SlugRelatedField(
      many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  not_activated = serializers.SerializerMethodField()

  class Meta:
    model = Course
    fields = ('id', 'organization', 'name', 'period', 'students', 'graders', 'superGraders', 'courseAdmins',
              'inactive_students', 'inactive_graders', 'inactive_courseAdmins', 'not_activated')
    read_only_fields = ('name', 'period', 'inactive_students', 'inactive_graders',
                        'inactive_courseAdmins', 'organization', 'not_activated')

  def get_not_activated(self, instance):
    return map(lambda x: x.email, list(set(
        list(instance.students.filter(is_active=False)) + list(instance.graders.filter(is_active=False)) +
        list(instance.courseAdmins.filter(is_active=False))
    )))

  def validate(self, data):
    newData = super().validate(data)
    newFields = self.genProposedFields(newData)

    if self.context['request'].user not in newFields['courseAdmins']:
      raise serializers.ValidationError(
          "User cannot remove itself as courseAdmin. Please request another courseAdmin to perform this action.")

    # Check that the list of courseAdmins is not empty
    if len(newFields['courseAdmins']) == 0:
      raise serializers.ValidationError("The courseAdmins list cannot be empty.")

    # If new set of students is being passed in, update inactives
    if 'students' in newData and self.instance:
      newInactives = []
      # Only students who are either (a) inactive or (b) in the course are candidates
      # to become inactive.
      studentSet = set(self.instance.students.all()).union(newFields['inactive_students'])

      for student in studentSet:
        if student not in newData['students']:
          newInactives.append(student)

      newData['inactive_students'] = newInactives

    # If new set of graders is being passed in, update inactives. The same
    # logic applies here as in the previous function
    if 'graders' in newData and self.instance:
      newInactives = []
      graderSet = set(self.instance.graders.all()).union(newFields['inactive_graders'])

      for grader in graderSet:
        if grader not in newData['graders']:
          newInactives.append(grader)

      newData['inactive_graders'] = newInactives

    # If new set of admins is being passed in, update inactives. The same logic applies here as in the student function
    if 'courseAdmins' in newData and self.instance:
      newInactives = []
      adminSet = set(self.instance.courseAdmins.all()).union(newFields['inactive_courseAdmins'])

      for admin in adminSet:
        if admin not in newData['courseAdmins']:
          newInactives.append(admin)

      newData['inactive_courseAdmins'] = newInactives

    # remove all superGraders who are not enrolled as graders.
    # This will occur if any grader is unenrolled or someone patches a non-grader to be a superGrader
    newSuperGraders = []
    for superGrader in newFields['superGraders']:
      if superGrader in newFields['graders']:
        newSuperGraders.append(superGrader)
    newData['superGraders'] = newSuperGraders

    # # Check to make sure that no student is a grader or course Admin
    # for student in newFields['students']:
    #   if student in newFields['graders']:
    #     raise serializers.ValidationError("The following user is listed as both a student and a grader: " + student.email)
    #   if student in newFields['courseAdmins']:
    #     raise serializers.ValidationError("The following user is listed as both a student and a course admin: " + student.email)

    # Check to make sure that all section students and leaders are still enrolled in the course, if they have been changed
    # NOTE: if self.instance is null, this statement will generate a 500 error. Leaving as-is for now; since we do not post
    # to this endpoint, self.instance should always be defined. If we decide this serializer is post-able in the future,
    # we will need to gate this block with <if self.instance>
    for section in self.instance.sections.all():
      if 'graders' in newData:
        for sectionLeader in section.leaders.all():
          if sectionLeader not in newFields['graders']:
            section.leaders.remove(sectionLeader)
      if 'students' in newData:
        for sectionStudent in section.students.all():
          if sectionStudent not in newFields['students']:
            section.students.remove(sectionStudent)
      section.save()

    return newData

