# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers

from core.serializers.rubricCategory import RubricCategorySerializer
from core.serializers.rubricComment import RubricCommentSerializer
from core.serializers.testCase import TestCaseStudentSerializer
from core.serializers.testCategory import TestCategorySerializer
from core.serializers.file import SubmissionFileStudentUploadSerializer
from core.serializers.submissionTest import SubmissionTestSerializer


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


class SubmissionCheckPermissionResponseSerializer(serializers.Serializer):
    read = serializers.BooleanField()
    write = serializers.BooleanField()
    filesOnly = serializers.BooleanField()


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
