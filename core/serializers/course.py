# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import pytz

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
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
  isRubricEditor = serializers.SerializerMethodField()

  cloneFrom = serializers.IntegerField(source='clone_from', write_only=True, required=False)
  expirationDate = serializers.DateTimeField(source='expiration_date', required=False, allow_null=True)

  class Meta:
    model = Course
    fields = ('id', 'name', 'period', 'assignments', 'sections', 'sendReleasedSubmissionsToBack',
              'showStudentsStatistics', 'timezone', 'emailNewUsers', 'anonymousGradingDefault', 'allowGradersToEditRubric', 
              'minComments', 'noUnfinalize', 'archived', 'lateDayCreditsAllowable', 'activateQueue', 'inviteCode', 'emailWhitelist', 
              'inviteCodeEnabled', 'enableStudentFeedbackNotifications', 'webhooks', 'expirationDate', 'organization', 'studentsCanSeeGraders', 'studentCount', 'isRubricEditor', 'cloneFrom')
    read_only_fields = ('assignments', 'sections', 'inviteCode', 'webhooks', 'studentCount', 'isRubricEditor')
    extra_kwargs = {
        'organization': {'required': False}
    }
    validators = []

  @extend_schema_field(serializers.IntegerField)
  def get_studentCount(self, obj):
    return obj.students.count()

  @extend_schema_field(serializers.BooleanField)
  def get_isRubricEditor(self, obj):
    request = self.context.get('request')
    if request and request.user.is_authenticated:
      return obj.rubricEditors.filter(pk=request.user.pk).exists()
    return False

  def validate_timezone(self, timezone):
    # Check that timezone corresponds to valid timezone
    options = pytz.all_timezones
    if timezone not in options:
      raise serializers.ValidationError("Timezone is not valid. See pytz.all_timezones for options.")
    return timezone

  @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
  def get_assignments(self, obj):
    
    if not self.context.get('request'):
      return []
    
    user = self.context.get('request').user  # type: ignore[union-attr]  # request is always present in this context

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
    clone_from_id = validated_data.pop('clone_from', None)

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

    # Handle cloning if requested
    if clone_from_id:
        try:
            source_course = Course.objects.get(id=clone_from_id)
            # Permission check: User must be admin of source course to clone its settings (esp. API keys)
            if isCourseStaff(courseAdmin, source_course) or courseAdmin.is_superuser:
                from core.utils import copy_assignment

                # Copy AI Settings
                obj.ai_provider = source_course.ai_provider
                obj.ai_api_key = source_course.ai_api_key  # Secure copy of encrypted key
                obj.ai_base_url = source_course.ai_base_url
                obj.ai_model = source_course.ai_model
                obj.ai_disabled = source_course.ai_disabled
                obj.ai_comments_disabled = source_course.ai_comments_disabled
                obj.ai_use_own_settings = source_course.ai_use_own_settings
                
                # Copy other settings if consistent with tooltips.tsx claim:
                # "Cloning a course will copy all assignments (including rubrics) and course settings"
                obj.sendReleasedSubmissionsToBack = source_course.sendReleasedSubmissionsToBack
                obj.showStudentsStatistics = source_course.showStudentsStatistics
                obj.emailNewUsers = source_course.emailNewUsers
                obj.anonymousGradingDefault = source_course.anonymousGradingDefault
                obj.allowGradersToEditRubric = source_course.allowGradersToEditRubric
                obj.minComments = source_course.minComments
                obj.noUnfinalize = source_course.noUnfinalize
                obj.lateDayCreditsAllowable = source_course.lateDayCreditsAllowable

                # Copy assignments into the new course
                for source_assignment in source_course.assignments.all().order_by('sortKey', 'id'):
                    copied_assignment = copy_assignment(source_assignment, obj)
                    if copied_assignment is None:
                        logger.warning(
                            "Failed to clone assignment %s while cloning course %s into course %s",
                            source_assignment.id,
                            source_course.id,
                            obj.id,
                        )
                
            else:
                 logger.warning(f"User {courseAdmin.email} tried to clone course {clone_from_id} without permission")

        except Course.DoesNotExist:
            logger.warning(f"Clone source course {clone_from_id} not found")

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
  aiProvider = serializers.ChoiceField(source='ai_provider', choices=Course.AI_PROVIDER_CHOICES, required=False, allow_null=True)
  aiApiKey = serializers.CharField(source='ai_api_key', required=False, allow_null=True, allow_blank=True, write_only=True)
  aiBaseUrl = serializers.CharField(source='ai_base_url', required=False, allow_null=True, allow_blank=True)
  aiModel = serializers.CharField(source='ai_model', required=False, allow_null=True, allow_blank=True)
  aiDisabled = serializers.BooleanField(source='ai_disabled', required=False)
  aiCommentsDisabled = serializers.BooleanField(source='ai_comments_disabled', required=False)
  aiUseOwnSettings = serializers.BooleanField(source='ai_use_own_settings', required=False)
  aiEnabled = serializers.SerializerMethodField()
  aiCommentsEnabled = serializers.SerializerMethodField()
  orgAiAvailable = serializers.SerializerMethodField()
  hasApiKey = serializers.SerializerMethodField()
  apiKeyHint = serializers.SerializerMethodField()
  aiTokenRates = serializers.JSONField(
    source='ai_token_rates', required=False, default=dict,
    help_text='Custom per-model token rates. JSON: {"model-name": {"input": 0.15, "output": 0.60}}',
  )
  defaultTokenRates = serializers.SerializerMethodField()
  
  class Meta:
    model = Course
    fields = (
      'id',
      'aiProvider',
      'aiApiKey',
      'aiBaseUrl',
      'aiModel',
      'aiDisabled',
      'aiCommentsDisabled',
      'aiUseOwnSettings',
      'aiTokenRates',
      'aiEnabled',
      'aiCommentsEnabled',
      'orgAiAvailable',
      'hasApiKey',
      'apiKeyHint',
      'defaultTokenRates',
    )

  @staticmethod
  def _provider_is_configured(provider, api_key):
    """Check if a provider has the credentials it needs. Portkey/Ollama only need a URL, not an API key."""
    if provider in ('ollama', 'portkey'):
      return bool(provider)
    return bool(provider and api_key)

  def _get_effective_ai_config(self, obj):
    """Returns the effective AI configuration for this course, considering org settings."""
    if obj.ai_use_own_settings:
      return {
        'provider': obj.ai_provider,
        'api_key': obj.ai_api_key,
        'disabled': obj.ai_disabled,
        'comments_disabled': obj.ai_comments_disabled,
      }
    # Check if org has AI enabled for this course
    org = obj.organization
    if org and not org.ai_disabled and org.ai_provider and self._provider_is_configured(org.ai_provider, org.ai_api_key):
      if org.ai_course_policy == 'all':
        return {
          'provider': org.ai_provider,
          'api_key': org.ai_api_key,
          'disabled': org.ai_disabled,
          'comments_disabled': org.ai_comments_disabled,
        }
      elif org.ai_course_policy == 'selected' and org.ai_enabled_courses.filter(pk=obj.pk).exists():
        return {
          'provider': org.ai_provider,
          'api_key': org.ai_api_key,
          'disabled': org.ai_disabled,
          'comments_disabled': org.ai_comments_disabled,
        }
    # Fall back to course's own settings
    return {
      'provider': obj.ai_provider,
      'api_key': obj.ai_api_key,
      'disabled': obj.ai_disabled,
      'comments_disabled': obj.ai_comments_disabled,
    }
  
  @extend_schema_field(serializers.BooleanField)
  def get_aiEnabled(self, obj):
    """Returns True if AI is configured and enabled for this course (considering org settings)."""
    config = self._get_effective_ai_config(obj)
    return self._provider_is_configured(config['provider'], config['api_key']) and not config['disabled']

  @extend_schema_field(serializers.BooleanField)
  def get_aiCommentsEnabled(self, obj):
    """Returns True if AI comments are available (considering org settings)."""
    config = self._get_effective_ai_config(obj)
    return self._provider_is_configured(config['provider'], config['api_key']) and not config['disabled'] and not config['comments_disabled']

  @extend_schema_field(serializers.BooleanField)
  def get_orgAiAvailable(self, obj):
    """Returns True if the organization has AI configured and this course is eligible to use it."""
    org = obj.organization
    if not org or org.ai_disabled or not org.ai_provider or not self._provider_is_configured(org.ai_provider, org.ai_api_key):
      return False
    if org.ai_course_policy == 'all':
      return True
    if org.ai_course_policy == 'selected':
      return org.ai_enabled_courses.filter(pk=obj.pk).exists()
    return False

  @extend_schema_field(serializers.BooleanField)
  def get_hasApiKey(self, obj):
    """Returns True if an API key has been saved for the effective configuration."""
    config = self._get_effective_ai_config(obj)
    return bool(config['api_key'])

  @extend_schema_field(serializers.CharField(allow_null=True))
  def get_apiKeyHint(self, obj):
    """Returns a masked preview of the effective API key, e.g. 'sk-…abc1'."""
    config = self._get_effective_ai_config(obj)
    return self._mask_key(config['api_key'])

  @extend_schema_field(serializers.DictField(child=serializers.DictField()))
  def get_defaultTokenRates(self, obj):
    """Returns the hardcoded default token rates from AIService."""
    from core.services.ai_service import AIService
    return {
      model: {'input': r[0], 'output': r[1]}
      for model, r in AIService.TOKEN_RATES.items()
    }

  @staticmethod
  def _mask_key(key):
    """Return a masked version of the key showing first 3 and last 4 chars."""
    if not key:
      return None
    k = str(key)
    if len(k) <= 8:
      return '••••' + k[-2:] if len(k) >= 2 else '••••••'
    return k[:3] + '…' + k[-4:]


class CourseRosterSerializer(ModelSerializerWithPOSTCheck):
  students = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  graders = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  superGraders = serializers.SlugRelatedField(
      many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  rubricEditors = serializers.SlugRelatedField(
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
    fields = ('id', 'organization', 'name', 'period', 'students', 'graders', 'superGraders', 'rubricEditors', 'courseAdmins',
              'inactive_students', 'inactive_graders', 'inactive_courseAdmins', 'not_activated')
    read_only_fields = ('name', 'period', 'inactive_students', 'inactive_graders',
                        'inactive_courseAdmins', 'organization', 'not_activated')

  @extend_schema_field(serializers.ListField(child=serializers.EmailField()))
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

    # remove all rubricEditors who are not enrolled as graders.
    # This will occur if any grader is unenrolled or someone patches a non-grader to be a rubricEditor
    newRubricEditors = []
    for rubricEditor in newFields['rubricEditors']:
      if rubricEditor in newFields['graders']:
        newRubricEditors.append(rubricEditor)
    newData['rubricEditors'] = newRubricEditors

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
    for section in self.instance.sections.all():  # type: ignore[union-attr]  # instance is always set for PATCH
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


class CourseRosterMapSerializer(serializers.Serializer):
  rosterMap = serializers.DictField(
      child=serializers.CharField(allow_blank=True, allow_null=True),
      required=False
  )


class CourseStudentCaptionsSerializer(serializers.Serializer):
  studentCaptions = serializers.DictField(
      child=serializers.CharField(allow_blank=True, allow_null=True),
      required=False
  )

