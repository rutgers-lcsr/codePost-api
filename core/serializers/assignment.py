from rest_framework import serializers
from core.logging import logEvent
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Assignment
from django.contrib.auth.models import User

from util.slack import Slack
from core.auth import Authentications, type_of_auth

from core.serializers.submission import SubmissionSerializer

from django.db.models import Max, Min, Avg


class AssignmentSerializerBase(ModelSerializerWithPOSTCheck):
  """
  Assignment Serializer from which all other Assignment Serializer subclasses inherit from
  """

  maxStudentTestRuns = serializers.SerializerMethodField('get_max_test_runs')
  exposeDumpLogs = serializers.SerializerMethodField('get_expose_dump_logs')
  nudgeMode = serializers.SerializerMethodField('get_nudge_mode')

  lateDeductions = serializers.JSONField(default=[])

  def get_max_test_runs(self, obj):
    if hasattr(obj, 'environment'):
      return obj.environment.maxStudentTestRuns
    else:
      return None

  def get_nudge_mode(self, obj):
    if hasattr(obj, 'environment'):
      return isinstance(obj.environment.maxExposedFailedTests, int)
    else:
      return False

  def get_expose_dump_logs(self, obj):
    if hasattr(obj, 'environment'):
      return obj.environment.exposeDumpLogs
    else:
      return None

  def validate(self, data):

    newData = super().validate(data)
    if 'lateDeductions' in newData:
      if not isinstance(newData['lateDeductions'], list):
        raise serializers.ValidationError("lateDeductions must be a list.")

      for deduction in newData['lateDeductions']:
        if not isinstance(deduction, int):
          raise serializers.ValidationError("lateDeductions must be numbers.")

    return newData

  class Meta:
    model = Assignment
    fields = ('id', 'name', 'isReleased', 'course', 'rubricCategories', 'allowStudentUpload', 'allowStudentUploadWithPartners',
              'uploadDueDate', 'liveFeedbackMode', 'allowLateUploads', 'environment', 'fileTemplates', 'maxStudentTestRuns', 'sortKey', 'exposeDumpLogs', 'explanation', 'isVisible', 'hideFrom', 'nudgeMode', 'lateDeductions')
    POST_permissions_fields = ('course',)
    read_only_fields = ('rubricCategories', 'fileTemplates', 'environment', 'maxStudentTestRuns', 'exposeDumpLogs', 'nudgeMode')


class AssignmentStudentSerializer(AssignmentSerializerBase):

  class Meta(AssignmentSerializerBase.Meta):
    read_only_fields = AssignmentSerializerBase.Meta.read_only_fields + \
        ('course', 'isReleased', 'name', 'sortKey', 'lateDeductions')


class AssignmentSerializer(AssignmentSerializerBase):

  class Meta(AssignmentSerializerBase.Meta):
    fields = AssignmentSerializerBase.Meta.fields + ('points', 'hideGrades', 'sortKey', 'anonymousGrading',
                                                     'hideGradersFromStudents', 'commentFeedback', 'additiveGrading', 'allowRegradeRequests', 'regradeInstructions',
                                                     'regradeDeadline', 'forcedRubricMode', 'templateMode', 'collaborativeRubricMode',
                                                     'testCategories',  'showFrequentlyUsedRubricComments')
    read_only_fields = AssignmentSerializerBase.Meta.read_only_fields + ('testCategories',)

  def create(self, validated_data):
    user = self.context['request'].user
    token = str(self.context['request'].auth)
    auth_type = type_of_auth(token)

    # Default to anonymous grading mode if field not overridden and course specifies we should use anonymous grading mode
    # by default
    if 'anonymousGrading' not in validated_data and validated_data['course'].anonymousGradingDefault:
      validated_data['anonymousGrading'] = True

    obj = super().create(validated_data)

    logEvent("Assignment Created",
             message=f"Assignment {obj.name} created by {user.email} with auth type {auth_type}")
    # Slack notification
    # sc = Slack()
    # sc.new_instance_notification(obj, user, auth_type)

    return obj


class AssignmentSerializerWithStatistics(AssignmentSerializer):

  class Meta(AssignmentSerializer.Meta):
    fields = AssignmentSerializer.Meta.fields + ('mean', 'median')
    read_only_fields = AssignmentSerializer.Meta.read_only_fields + ('mean', 'median')


class AssignmentSerializerWithStatisticsAndSummary(AssignmentSerializerWithStatistics):
  submissions_count = serializers.SerializerMethodField()
  submissions_finalized_count = serializers.SerializerMethodField()
  submissions_inprogress_count = serializers.SerializerMethodField()
  submissions_unclaimed_count = serializers.SerializerMethodField()
  submissions_missing_count = serializers.SerializerMethodField()

  stats_max = serializers.SerializerMethodField()
  stats_min = serializers.SerializerMethodField()
  stats_mean = serializers.SerializerMethodField()

  class Meta(AssignmentSerializerWithStatistics.Meta):
    fields = AssignmentSerializerWithStatistics.Meta.fields + \
        ('submissions_count', 'submissions_finalized_count', 'submissions_inprogress_count',
         'submissions_unclaimed_count', 'submissions_missing_count', 'stats_max', 'stats_min',
         'stats_mean')

  def get_submissions_count(self, obj):
    return obj.submissions.count()

  def get_submissions_finalized_count(self, obj):
    return obj.submissions.filter(isFinalized=True).count()

  def get_submissions_inprogress_count(self, obj):
    return obj.submissions.filter(isFinalized=False).exclude(grader=None).count()

  def get_submissions_unclaimed_count(self, obj):
    return obj.submissions.filter(grader=None).count()

  def get_submissions_missing_count(self, obj):
    all_students = User.objects.filter(student_courses=obj.course)
    num_students = all_students.count()
    submitted_students = all_students.filter(student_submissions__assignment=obj).count()
    return num_students - submitted_students

  def get_stats_max(self, obj):
    stats_max = obj.submissions.filter(isFinalized=True).aggregate(Max('grade'))['grade__max']

    if stats_max:
      return stats_max
    else:
      return 0

  def get_stats_min(self, obj):
    stats_min = obj.submissions.filter(isFinalized=True).aggregate(Min('grade'))['grade__min']

    if stats_min:
      return stats_min
    else:
      return 0

  def get_stats_mean(self, obj):
    stats_mean = obj.submissions.filter(isFinalized=True).aggregate(Avg('grade'))['grade__avg']
    if stats_mean:
      return stats_mean
    else:
      return 0


class MoocAssignmentSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = Assignment
    fields = ('id', 'name', 'course', 'sortKey')
