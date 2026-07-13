# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.permissions.capabilities import Capability
from core.serializers.rubricCategory import RubricCategorySerializer
from core.serializers.rubricComment import RubricCommentSerializer
from core.serializers.testCase import TestCaseStudentSerializer
from core.serializers.testCategory import TestCategorySerializer
from core.serializers.file import SubmissionFileStudentUploadSerializer
from core.serializers.submissionTest import SubmissionTestSerializer


def _capability_map_schema() -> dict:
    """Build an OpenAPI schema object with every ``Capability`` member as a
    boolean property.  This causes ``drf-spectacular`` to emit explicit keys
    in ``schema.yaml`` so that the generated TypeScript client gets a typed
    interface instead of ``{ [key: string]: boolean }``.
    """
    return {
        "type": "object",
        "properties": {
            cap.value: {"type": "boolean"} for cap in Capability
        },
    }


@extend_schema_field(_capability_map_schema())
class CapabilityMapField(serializers.DictField):
    """``DictField`` whose OpenAPI schema lists every capability key explicitly."""
    child = serializers.BooleanField()


class AssignmentQueueLengthResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    unclaimed = serializers.IntegerField()
    finalized = serializers.IntegerField()
    unfinalized = serializers.IntegerField()


class AssignmentRubricResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    rubricCategories = RubricCategorySerializer(many=True)
    rubricComments = RubricCommentSerializer(many=True)


class AssignmentStudentTestsResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    testCases = TestCaseStudentSerializer(many=True)
    testCategories = TestCategorySerializer(many=True)


class BeforeStudentUploadResponseSerializer(serializers.Serializer):
    daysLate = serializers.IntegerField()
    pointsOff = serializers.FloatField()
    lateDayCreditsAvailable = serializers.IntegerField(required=False)
    lateDayCreditsToUse = serializers.IntegerField(required=False)
    adjustedDaysLate = serializers.IntegerField(required=False)


class AssignmentDownloadResponseSerializer(serializers.Serializer):
    zip = serializers.CharField()
    filename = serializers.CharField()


class AssignmentStudentUploadGetResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    files = SubmissionFileStudentUploadSerializer(many=True)


class CapabilitiesResponseSerializer(serializers.Serializer):
    """Serializer for the capabilities endpoint.

    Returns ``{ "capabilitiesMap": { cap_key: bool, ... } }``.
    The field is named in camelCase so the API response matches the
    generated TypeScript client property name (no camelCase renderer
    middleware is installed).
    """

    capabilitiesMap = CapabilityMapField(
        help_text="Map of capability keys to boolean values.",
    )


class CapabilitiesWithDescriptionsResponseSerializer(serializers.Serializer):
    """Response when ``?descriptions=true`` is set."""
    capabilities = CapabilityMapField()
    descriptions = serializers.DictField(child=serializers.CharField())


class SubmissionCheckPermissionResponseSerializer(serializers.Serializer):
    read = serializers.BooleanField()
    write = serializers.BooleanField()
    filesOnly = serializers.BooleanField()
    capabilities = CapabilityMapField(required=False)


class BatchCapabilitiesRequestSerializer(serializers.Serializer):
    """Request body for ``POST /capabilities/batch/``.

    Each key must be ``"course:{id}"``, ``"assignment:{id}"``,
    ``"submission:{id}"``, or ``"platform"``.
    """
    keys = serializers.ListField(
        child=serializers.CharField(max_length=64),
        max_length=20,
        help_text='List of resource keys, e.g. ["course:1", "assignment:5", "submission:42", "platform"].',
    )


class BatchCapabilitiesResponseSerializer(serializers.Serializer):
    """Response for ``POST /capabilities/batch/``.

    Returns ``{ results: { "course:1": { ... }, "assignment:5": { ... } } }``.
    """
    results = serializers.DictField(
        child=CapabilityMapField(),
        help_text="Map of resource keys to their capability maps.",
    )


class LearningObjectiveSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    shortId = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    met = serializers.BooleanField()
    score = serializers.FloatField()
    aggregationMode = serializers.CharField()


class SubmissionTestResultsResponseSerializer(serializers.Serializer):
    submissionTests = SubmissionTestSerializer(many=True)
    logs = serializers.CharField()
    learningObjectives = LearningObjectiveSummarySerializer(many=True, required=False)


class SubmissionPartnerLinkResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    token = serializers.CharField()


class TestCaseRunRequestSerializer(serializers.Serializer):
    submission = serializers.IntegerField(required=False, allow_null=True)
    files = serializers.JSONField(required=False)


class TestCaseRunResponseSerializer(serializers.Serializer):
    task = serializers.CharField()


# ============================================================================
# Assignment Analytics
# ============================================================================

class AssignmentAnalyticsGradeDistributionSerializer(serializers.Serializer):
    bucketMin = serializers.FloatField()
    bucketMax = serializers.FloatField()
    count = serializers.IntegerField()


class AssignmentAnalyticsGraderWorkloadSerializer(serializers.Serializer):
    grader = serializers.CharField()
    finalized = serializers.IntegerField()
    unfinalized = serializers.IntegerField()
    total = serializers.IntegerField()


class AssignmentAnalyticsGradingTimelineSerializer(serializers.Serializer):
    period = serializers.CharField()
    count = serializers.IntegerField()


class AssignmentAnalyticsTestResultsSerializer(serializers.Serializer):
    testCaseDescription = serializers.CharField()
    testCategoryName = serializers.CharField()
    passed = serializers.IntegerField()
    failed = serializers.IntegerField()
    errored = serializers.IntegerField()
    total = serializers.IntegerField()


class AssignmentAnalyticsRubricUsageSerializer(serializers.Serializer):
    rubricCommentId = serializers.IntegerField()
    text = serializers.CharField()
    pointDelta = serializers.FloatField()
    categoryName = serializers.CharField()
    count = serializers.IntegerField()


class AssignmentAnalyticsScoreByCategorySerializer(serializers.Serializer):
    categoryName = serializers.CharField()
    pointLimit = serializers.FloatField(allow_null=True)
    meanDeduction = serializers.FloatField()
    medianDeduction = serializers.FloatField()
    minDeduction = serializers.FloatField()
    maxDeduction = serializers.FloatField()
    submissionCount = serializers.IntegerField()


class AssignmentAnalyticsGraderConsistencySerializer(serializers.Serializer):
    grader = serializers.CharField()
    meanGrade = serializers.FloatField(allow_null=True)
    stddevGrade = serializers.FloatField(allow_null=True)
    count = serializers.IntegerField()


class AssignmentAnalyticsAttemptDistributionSerializer(serializers.Serializer):
    attempts = serializers.IntegerField()
    studentCount = serializers.IntegerField()


class AssignmentAnalyticsSubmissionAttemptsSerializer(serializers.Serializer):
    attemptDistribution = AssignmentAnalyticsAttemptDistributionSerializer(many=True)
    avgGradeImprovement = serializers.FloatField(allow_null=True)
    studentsWithMultipleAttempts = serializers.IntegerField()
    totalStudents = serializers.IntegerField()


class AssignmentAnalyticsTurnaroundStatsSerializer(serializers.Serializer):
    meanHours = serializers.FloatField(allow_null=True)
    medianHours = serializers.FloatField(allow_null=True)
    minHours = serializers.FloatField(allow_null=True)
    maxHours = serializers.FloatField(allow_null=True)


class AssignmentAnalyticsGraderTurnaroundSerializer(serializers.Serializer):
    grader = serializers.CharField()
    count = serializers.IntegerField()
    meanHours = serializers.FloatField(allow_null=True)
    medianHours = serializers.FloatField(allow_null=True)
    minHours = serializers.FloatField(allow_null=True)
    maxHours = serializers.FloatField(allow_null=True)


class AssignmentAnalyticsTimeToGradeSerializer(serializers.Serializer):
    overall = AssignmentAnalyticsTurnaroundStatsSerializer(allow_null=True)
    byGrader = AssignmentAnalyticsGraderTurnaroundSerializer(many=True)


class AssignmentAnalyticsLateByDaySerializer(serializers.Serializer):
    day = serializers.IntegerField()
    count = serializers.IntegerField()


class AssignmentAnalyticsLateSubmissionsSerializer(serializers.Serializer):
    dueDate = serializers.CharField()
    onTime = serializers.IntegerField()
    late = serializers.IntegerField()
    lateByDay = AssignmentAnalyticsLateByDaySerializer(many=True)


class AssignmentAnalyticsFeedbackOverallSerializer(serializers.Serializer):
    meanCommentsPerSubmission = serializers.FloatField()
    medianCommentsPerSubmission = serializers.FloatField()
    totalSubmissionsWithComments = serializers.IntegerField()


class AssignmentAnalyticsGraderFeedbackSerializer(serializers.Serializer):
    grader = serializers.CharField()
    totalComments = serializers.IntegerField()
    rubricComments = serializers.IntegerField()
    freeformComments = serializers.IntegerField()
    submissionsGraded = serializers.IntegerField()
    meanComments = serializers.FloatField()


class AssignmentAnalyticsFeedbackDepthSerializer(serializers.Serializer):
    overall = AssignmentAnalyticsFeedbackOverallSerializer(allow_null=True)
    byGrader = AssignmentAnalyticsGraderFeedbackSerializer(many=True)


class AssignmentAnalyticsResponseSerializer(serializers.Serializer):
    gradeDistribution = AssignmentAnalyticsGradeDistributionSerializer(many=True)
    graderWorkload = AssignmentAnalyticsGraderWorkloadSerializer(many=True)
    gradingTimeline = AssignmentAnalyticsGradingTimelineSerializer(many=True)
    testResults = AssignmentAnalyticsTestResultsSerializer(many=True)
    rubricUsage = AssignmentAnalyticsRubricUsageSerializer(many=True)
    scoreByCategory = AssignmentAnalyticsScoreByCategorySerializer(many=True)
    graderConsistency = AssignmentAnalyticsGraderConsistencySerializer(many=True)
    submissionAttempts = AssignmentAnalyticsSubmissionAttemptsSerializer(required=False, allow_null=True)
    timeToGrade = AssignmentAnalyticsTimeToGradeSerializer(required=False, allow_null=True)
    lateSubmissions = AssignmentAnalyticsLateSubmissionsSerializer(required=False, allow_null=True)
    feedbackDepth = AssignmentAnalyticsFeedbackDepthSerializer(required=False, allow_null=True)
