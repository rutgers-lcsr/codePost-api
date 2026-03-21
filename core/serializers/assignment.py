# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.logging import logEvent
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Assignment
from django.contrib.auth.models import User

from core.auth import Authentications, type_of_auth

from core.serializers.submission import SubmissionSerializer

from django.db.models import Max, Min, Avg


from core.serializers.file import AssignmentFilePublicSerializer

class AssignmentSerializerBase(ModelSerializerWithPOSTCheck):
  """
  Assignment Serializer from which all other Assignment Serializer subclasses inherit from
  """

  maxStudentTestRuns = serializers.SerializerMethodField('get_max_test_runs')
  nudgeMode = serializers.SerializerMethodField('get_nudge_mode')
  files = serializers.SerializerMethodField('get_files')
  dataSets = serializers.SerializerMethodField('get_datasets')
  fileTemplates = serializers.SerializerMethodField('get_file_templates')

  lateDeductions = serializers.JSONField(default=[])  # type: ignore[arg-type]  # DRF accepts list as default

  @extend_schema_field(serializers.IntegerField(allow_null=True))
  def get_max_test_runs(self, obj):
    if hasattr(obj, 'environment'):
      return obj.environment.maxStudentTestRuns
    else:
      return None

  @extend_schema_field(serializers.BooleanField)
  def get_nudge_mode(self, obj):
    if hasattr(obj, 'environment'):
      return isinstance(obj.environment.maxExposedFailedTests, int)
    else:
      return False


  @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
  def get_files(self, obj):
    # Return IDs of AssignmentFile objects
    return list(obj.files.values_list('id', flat=True))

  @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
  def get_datasets(self, obj):
    # Return IDs of AssignmentDataSet objects
    return list(obj.dataSets.values_list('id', flat=True))

  @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
  def get_file_templates(self, obj):
    # FileTemplate is deprecated - return empty array for backwards compatibility
    return []

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
    fields = ('id', 'name', 'isReleased', 'feedbackReleased', 'course', 'rubricCategories', 'allowStudentUpload', 'allowStudentUploadWithPartners',
              'uploadDueDate', 'maxLateDays', 'liveFeedbackMode', 'allowLateUploads', 'environment', 'files', 'fileTemplates', 'maxStudentTestRuns', 'sortKey', 'explanation', 'isVisible', 'hideFrom', 'nudgeMode', 'lateDeductions', 'studentsCanSeeGraders', 'dataSets')
    POST_permissions_fields = ('course',)
    read_only_fields = ('rubricCategories', 'environment', 'files', 'fileTemplates', 'maxStudentTestRuns', 'nudgeMode', 'dataSets')


class AssignmentStudentSerializer(AssignmentSerializerBase):

  class Meta(AssignmentSerializerBase.Meta):
    read_only_fields = AssignmentSerializerBase.Meta.read_only_fields + \
        ('course', 'isReleased', 'feedbackReleased', 'name', 'sortKey', 'lateDeductions')

  def get_files(self, obj):
    return AssignmentFilePublicSerializer(obj.files.all(), many=True).data


class AssignmentSerializer(AssignmentSerializerBase):

  class Meta(AssignmentSerializerBase.Meta):
    fields = AssignmentSerializerBase.Meta.fields + ('points', 'hideGrades', 'sortKey', 'anonymousGrading',
                                                     'hideGradersFromStudents', 'commentFeedback', 'additiveGrading', 'allowRegradeRequests', 'regradeInstructions',
                                                     'regradeDeadline', 'forcedRubricMode', 'templateMode', 'collaborativeRubricMode', 'gradersCanEditSubmissions',
                                                     'testCategories', 'showFrequentlyUsedRubricComments', 'ai_system_prompt', 'runFilesOnSubmit', 'runTestsOnSubmit', 'testsAffectGrade')
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

    return obj


class AssignmentStudentSerializerNoStats(AssignmentSerializer):
  def get_files(self, obj):
    return AssignmentFilePublicSerializer(obj.files.all(), many=True).data

class AssignmentSerializerWithStatistics(AssignmentSerializer):

  class Meta(AssignmentSerializer.Meta):
    fields = AssignmentSerializer.Meta.fields + ('mean', 'median')
    read_only_fields = AssignmentSerializer.Meta.read_only_fields + ('mean', 'median')


class AssignmentStudentSerializerWithStats(AssignmentSerializerWithStatistics):
  def get_files(self, obj):
    return AssignmentFilePublicSerializer(obj.files.all(), many=True).data


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




  @extend_schema_field(serializers.IntegerField)
  def get_submissions_count(self, obj):
    val = getattr(obj, 'submissions_count_anno', None)
    if val is not None:
      return val
    return obj.submissions.count()

  @extend_schema_field(serializers.IntegerField)
  def get_submissions_finalized_count(self, obj):
    val = getattr(obj, 'submissions_finalized_count_anno', None)
    if val is not None:
      return val
    return obj.submissions.filter(isFinalized=True).count()

  @extend_schema_field(serializers.IntegerField)
  def get_submissions_inprogress_count(self, obj):
    val = getattr(obj, 'submissions_inprogress_count_anno', None)
    if val is not None:
      return val
    return obj.submissions.filter(isFinalized=False).exclude(grader=None).count()

  @extend_schema_field(serializers.IntegerField)
  def get_submissions_unclaimed_count(self, obj):
    val = getattr(obj, 'submissions_unclaimed_count_anno', None)
    if val is not None:
      return val
    return obj.submissions.filter(grader=None).count()

  @extend_schema_field(serializers.IntegerField)
  def get_submissions_missing_count(self, obj):
    all_students = User.objects.filter(student_courses=obj.course)
    num_students = all_students.count()
    submitted_students = all_students.filter(student_submissions__assignment=obj).count()
    return num_students - submitted_students

  @extend_schema_field(serializers.FloatField)
  def get_stats_max(self, obj):
    val = getattr(obj, 'stats_max_anno', None)
    if val is not None:
      return val
    stats_max = obj.submissions.filter(isFinalized=True).aggregate(Max('grade'))['grade__max']
    return stats_max or 0

  @extend_schema_field(serializers.FloatField)
  def get_stats_min(self, obj):
    val = getattr(obj, 'stats_min_anno', None)
    if val is not None:
      return val
    stats_min = obj.submissions.filter(isFinalized=True).aggregate(Min('grade'))['grade__min']
    return stats_min or 0

  @extend_schema_field(serializers.FloatField)
  def get_stats_mean(self, obj):
    val = getattr(obj, 'stats_mean_anno', None)
    if val is not None:
      return val
    stats_mean = obj.submissions.filter(isFinalized=True).aggregate(Avg('grade'))['grade__avg']
    return stats_mean or 0



    return stats_mean or 0


class AssignmentCloneSerializer(serializers.Serializer):
  course = serializers.IntegerField(help_text="ID of the destination course")

class AssignmentGenerateTestSerializer(serializers.Serializer):
  targetFilename = serializers.CharField(source='target_filename', help_text="Name of the file to test (e.g., 'main.py')")
  contextFileId = serializers.IntegerField(source='context_file_id', required=False, help_text="ID of an AssignmentFile to use as context")
  contextFileName = serializers.CharField(source='context_file_name', required=False, help_text="Name of an AssignmentFile to use as context")
  language = serializers.CharField(required=False, default='python', help_text="Target language")
  rubricText = serializers.CharField(source='rubric_text', required=False, allow_blank=True, help_text="Rubric context for test generation")

class AssignmentGenerateTestResponseSerializer(serializers.Serializer):
  script = serializers.CharField(help_text="The generated test script")
