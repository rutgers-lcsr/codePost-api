# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.logging import logEvent
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Assignment, ASSIGNMENT_STATE_CHOICES, STUDENT_VISIBLE_STATES
from django.contrib.auth.models import User

from core.auth import type_of_auth


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
  effectiveState = serializers.SerializerMethodField('get_effective_state')
  # Legacy read-only compatibility: the DB columns are gone (work axis Phase 4,
  # feedback axis Phase 5), but consumers that READ these keep working. Writes are
  # rejected in validate() below.
  isVisible = serializers.SerializerMethodField('get_is_visible')
  isReleased = serializers.SerializerMethodField('get_is_released')
  feedbackReleased = serializers.SerializerMethodField('get_feedback_released')
  liveFeedbackMode = serializers.SerializerMethodField('get_live_feedback_mode')

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

  @extend_schema_field(serializers.ChoiceField(choices=ASSIGNMENT_STATE_CHOICES))
  def get_effective_state(self, obj):
    # The badge clients render: stored state, except a past-deadline published
    # assignment reads as closed. Nobody reimplements the deadline math.
    return obj.effective_state()

  @extend_schema_field(serializers.BooleanField)
  def get_is_visible(self, obj):
    return obj.state in STUDENT_VISIBLE_STATES

  @extend_schema_field(serializers.BooleanField)
  def get_is_released(self, obj):
    return obj.state in ('published', 'closed')

  @extend_schema_field(serializers.BooleanField)
  def get_feedback_released(self, obj):
    return obj.feedbackStatus == 'released'

  @extend_schema_field(serializers.BooleanField)
  def get_live_feedback_mode(self, obj):
    return obj.feedbackStatus == 'live'

  def validate(self, data):

    newData = super().validate(data)
    if 'lateDeductions' in newData:
      if not isinstance(newData['lateDeductions'], list):
        raise serializers.ValidationError("lateDeductions must be a list.")

      for deduction in newData['lateDeductions']:
        if not isinstance(deduction, int):
          raise serializers.ValidationError("lateDeductions must be numbers.")

    # Deprecation shim (until Phase 4): the legacy booleans are read-only, derived from
    # state. Reject writes loudly instead of letting them silently no-op.
    if self.initial_data is not None:
      for legacy in ('isVisible', 'isReleased'):
        if legacy in self.initial_data:
          raise serializers.ValidationError({
              legacy: f"{legacy} is read-only — set state "
                      "(draft/visible/preview/published/closed/archived) instead."})
      for legacy in ('feedbackReleased', 'liveFeedbackMode'):
        if legacy in self.initial_data:
          raise serializers.ValidationError({
              legacy: f"{legacy} is read-only — set feedbackStatus "
                      "(hidden/live/per_student/released) instead."})

    # A scheduled publish time only makes sense before the assignment is published.
    # Only enforce when this change introduces the bad pairing (legacy rows stay editable).
    proposed_state = newData.get('state', getattr(self.instance, 'state', 'draft'))
    proposed_publish_at = newData.get('publishAt', getattr(self.instance, 'publishAt', None))
    already_bad = (self.instance is not None and self.instance.publishAt is not None
                   and self.instance.state in ('published', 'closed', 'archived'))
    if (proposed_publish_at is not None and proposed_state in ('published', 'closed', 'archived')
        and not already_bad):
      if newData.get('state') in ('published', 'closed', 'archived') and 'publishAt' not in newData:
        # Publishing (or closing/archiving) an assignment that had a schedule: the
        # schedule is moot — clear it rather than reject the transition.
        newData['publishAt'] = None
      else:
        raise serializers.ValidationError({
            'publishAt': "A scheduled publish time can only be set while the assignment "
                         "is draft, visible, or preview."})

    # A scheduled feedback release only makes sense before feedback is out. Same
    # only-enforce-when-introduced idiom as publishAt above.
    proposed_fstatus = newData.get('feedbackStatus', getattr(self.instance, 'feedbackStatus', 'hidden'))
    proposed_release_at = newData.get('releaseFeedbackAt', getattr(self.instance, 'releaseFeedbackAt', None))
    already_bad_release = (self.instance is not None and self.instance.releaseFeedbackAt is not None
                           and self.instance.feedbackStatus in ('released', 'live'))
    if (proposed_release_at is not None and proposed_fstatus in ('released', 'live')
        and not already_bad_release):
      if newData.get('feedbackStatus') in ('released', 'live') and 'releaseFeedbackAt' not in newData:
        # Releasing (or going live) with a schedule pending: the schedule is moot.
        newData['releaseFeedbackAt'] = None
      else:
        raise serializers.ValidationError({
            'releaseFeedbackAt': "A scheduled feedback release can only be set while "
                                 "feedback is hidden or per-student."})

    # per_student has no global feedback-release moment — attached quizzes anchored on
    # one can never fire. Block the switch while such quizzes exist.
    if (newData.get('feedbackStatus') == 'per_student' and self.instance is not None
        and self.instance.feedbackStatus != 'per_student'):
      from django.db.models import Q
      conflicting = self.instance.quizzes.filter(
          Q(assignmentTrigger='after_feedback') | Q(closeEvent='feedback_released')).count()
      if conflicting:
        raise serializers.ValidationError({
            'feedbackStatus': f"{conflicting} attached quiz(zes) open or close on the "
                              "whole-assignment feedback release, which per-student "
                              "feedback does not have. Change those quizzes to the "
                              "self-paced trigger first."})

    return newData

  def validate_hideFrom(self, sections):
    # Nothing else checks this: a section from another course must not be attachable.
    if not sections:
      return sections
    if self.instance is not None:
      course_id = self.instance.course_id
    else:
      course_id = self.initial_data.get('course')
    if course_id is None:
      return sections  # create without course fails field validation elsewhere
    for section in sections:
      if section.course_id != int(course_id):
        raise serializers.ValidationError(
            "hideFrom sections must belong to the assignment's course.")
    return sections

  class Meta:
    model = Assignment
    fields = ('id', 'name', 'state', 'effectiveState', 'publishedAt', 'publishAt', 'scheduledPublishRanAt', 'isReleased', 'feedbackStatus', 'releaseFeedbackAt', 'scheduledFeedbackReleaseRanAt', 'feedbackReleased', 'course', 'rubricCategories', 'allowStudentUpload', 'allowStudentUploadWithPartners',
              'uploadDueDate', 'maxLateDays', 'liveFeedbackMode', 'allowLateUploads', 'environment', 'files', 'fileTemplates', 'maxStudentTestRuns', 'sortKey', 'explanation', 'isVisible', 'hideFrom', 'nudgeMode', 'lateDeductions', 'studentsCanSeeGraders', 'dataSets')
    POST_permissions_fields = ('course',)
    # scheduledPublishRanAt is the one-shot stamp of the scheduled publish sweep.
    # (isVisible/isReleased are declared SerializerMethodFields — read-only by nature.)
    read_only_fields = ('rubricCategories', 'environment', 'files', 'fileTemplates', 'maxStudentTestRuns', 'nudgeMode', 'dataSets',
                        'effectiveState', 'publishedAt', 'scheduledPublishRanAt', 'scheduledFeedbackReleaseRanAt')


class AssignmentStudentSerializer(AssignmentSerializerBase):

  class Meta(AssignmentSerializerBase.Meta):
    read_only_fields = AssignmentSerializerBase.Meta.read_only_fields + \
        ('course', 'state', 'publishAt', 'feedbackStatus', 'releaseFeedbackAt', 'name', 'sortKey', 'lateDeductions')

  def get_files(self, obj):
    return AssignmentFilePublicSerializer(obj.files.all(), many=True).data


class AssignmentSerializer(AssignmentSerializerBase):

  class Meta(AssignmentSerializerBase.Meta):
    fields = AssignmentSerializerBase.Meta.fields + ('points', 'hideGrades', 'sortKey', 'anonymousGrading',
                                                     'hideGradersFromStudents', 'commentFeedback', 'additiveGrading', 'allowRegradeRequests', 'regradeInstructions',
                                                     'regradeDeadline', 'forcedRubricMode', 'templateMode', 'collaborativeRubricMode', 'gradersCanEditSubmissions',
                                                     'testCategories', 'showFrequentlyUsedRubricComments', 'ai_system_prompt',
                                                     'ai_summary_prompt', 'ai_description', 'ai_description_locked',
                                                     'runFilesOnSubmit', 'runTestsOnSubmit', 'testsAffectGrade')
    read_only_fields = AssignmentSerializerBase.Meta.read_only_fields + ('testCategories',)


  def validate(self, data):
    data = super().validate(data)
    self._validate_prompt_placeholders(data, 'ai_system_prompt', 'comment_generation')
    self._validate_prompt_placeholders(data, 'ai_summary_prompt', 'submission_summary')
    return data

  @staticmethod
  def _validate_prompt_placeholders(data, field, prompt_type):
    """Reject a per-assignment prompt override that uses {placeholders} outside the
    prompt type's allowed set — same check the Prompt Lab applies to global variants
    (see core/serializers/prompt_variant.py)."""
    template = data.get(field)
    if not template:
      return
    import string
    from core.prompts.registry import prompt_registry
    allowed = prompt_registry.get_allowed_placeholders(prompt_type)
    used = set()
    try:
      for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name is not None:
          root = field_name.split('.')[0].split('[')[0]
          if root:
            used.add(root)
    except (ValueError, KeyError):
      raise serializers.ValidationError({
          field: 'Invalid template syntax. Check for unmatched or malformed {placeholders}.'
      })
    invalid = used - allowed
    if invalid:
      raise serializers.ValidationError({
          field: (f"Unknown placeholder(s): {{{', '.join(sorted(invalid))}}}. "
                  f"Allowed placeholders: {{{', '.join(sorted(allowed))}}}.")
      })

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


# Fields beyond the pre-feedback student view that a post-feedback student legitimately
# needs — verified against the student UI (grade breakdown, comment feedback, regrade
# UI, tests tab). Staff-only fields (ai_* prompts, anonymousGrading, forcedRubricMode,
# gradersCanEditSubmissions, ...) must NOT appear here: the leak-guard tests in
# core/tests/serializers/test_assignment.py enforce the exact field set.
STUDENT_RELEASED_EXTRA_FIELDS = (
    'points', 'hideGrades', 'commentFeedback', 'additiveGrading',
    'allowRegradeRequests', 'regradeInstructions', 'regradeDeadline',
    'testsAffectGrade',
)


class AssignmentStudentSerializerNoStats(AssignmentStudentSerializer):
  """Post-feedback student view: the student base (public files) plus the released
  extras — NOT the staff serializer, which leaks staff-only fields."""

  class Meta(AssignmentStudentSerializer.Meta):
    fields = AssignmentSerializerBase.Meta.fields + STUDENT_RELEASED_EXTRA_FIELDS
    read_only_fields = AssignmentStudentSerializer.Meta.read_only_fields + STUDENT_RELEASED_EXTRA_FIELDS


class AssignmentSerializerWithStatistics(AssignmentSerializer):

  class Meta(AssignmentSerializer.Meta):
    fields = AssignmentSerializer.Meta.fields + ('mean', 'median')
    read_only_fields = AssignmentSerializer.Meta.read_only_fields + ('mean', 'median')


class AssignmentStudentSerializerWithStats(AssignmentStudentSerializerNoStats):

  class Meta(AssignmentStudentSerializerNoStats.Meta):
    fields = AssignmentStudentSerializerNoStats.Meta.fields + ('mean', 'median')
    read_only_fields = AssignmentStudentSerializerNoStats.Meta.read_only_fields + ('mean', 'median')


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

  @extend_schema_field(serializers.FloatField(allow_null=True))
  def get_stats_max(self, obj):
    val = getattr(obj, 'stats_max_anno', None)
    if val is not None:
      return val
    # None (no finalized submissions) stays None — coercing to 0 made an
    # ungraded assignment read as a real 0-point average.
    return obj.submissions.filter(isFinalized=True).aggregate(Max('grade'))['grade__max']

  @extend_schema_field(serializers.FloatField(allow_null=True))
  def get_stats_min(self, obj):
    val = getattr(obj, 'stats_min_anno', None)
    if val is not None:
      return val
    # None (no finalized submissions) stays None — coercing to 0 made an
    # ungraded assignment read as a real 0-point average.
    return obj.submissions.filter(isFinalized=True).aggregate(Min('grade'))['grade__min']

  @extend_schema_field(serializers.FloatField(allow_null=True))
  def get_stats_mean(self, obj):
    val = getattr(obj, 'stats_mean_anno', None)
    if val is not None:
      return val
    # None (no finalized submissions) stays None — coercing to 0 made an
    # ungraded assignment read as a real 0-point average.
    return obj.submissions.filter(isFinalized=True).aggregate(Avg('grade'))['grade__avg']


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
