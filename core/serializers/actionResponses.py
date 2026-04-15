# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
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


class SubmissionTestResultsResponseSerializer(serializers.Serializer):
    submissionTests = SubmissionTestSerializer(many=True)
    logs = serializers.CharField()


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


class AssignmentAnalyticsResponseSerializer(serializers.Serializer):
    gradeDistribution = AssignmentAnalyticsGradeDistributionSerializer(many=True)
    graderWorkload = AssignmentAnalyticsGraderWorkloadSerializer(many=True)
    gradingTimeline = AssignmentAnalyticsGradingTimelineSerializer(many=True)
    testResults = AssignmentAnalyticsTestResultsSerializer(many=True)
