# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import TestCase
from core.serializers.testCase import TestCaseSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import TestCasePermissions
from core.models import Submission
from core.permissions.helpers import isStaffOfSub, returnNotAuthorized

from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema
from core.serializers.actionResponses import TestCaseRunRequestSerializer, TestCaseRunResponseSerializer
from core.permissions.capabilities import require_capability
from core.permissions.helpers import isAuthenticated, returnForbidden

from core.permissions.helpers import isCourseAdmin, isCourseStaff

from rest_framework.response import Response

from rest_framework import serializers

import json

from autograder.run import Run, RunType


class TestCaseViewSet(ListProtectedViewSet):
    """
    list:
    Return a list of all the testcases.

    create:
    Create a new testcases.

    retrieve:
    Return the given testcases.

    update:
    Update a testcases.

    partial_update:
    Update a testcases.

    delete:
    Delete a testcases.
    """

    queryset = TestCase.objects.all()
    serializer_class = TestCaseSerializer
    permission_classes = (IsAuthenticated, TestCasePermissions)

    @extend_schema(request=TestCaseRunRequestSerializer, responses=TestCaseRunResponseSerializer)
    @action(detail=True, methods=["POST"])
    def run(self, request, pk=None):
        user = self.request.user
        testCase = TestCase.objects.get(id=pk)
        assignment = testCase.testCategory.assignment
        course = assignment.course

        if not isAuthenticated(user):
            return returnNotAuthorized()

        require_capability(user, 'manage_test_cases', assignment)

        if not assignment.environment or not assignment.environment.language:
            raise serializers.ValidationError(
                "Environment has not been created for this asignment."
            )

        serializer = TestCaseRunRequestSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        if not isinstance(validated_data, dict):
            validated_data = {}

        submission = validated_data.get("submission", None)
        files = validated_data.get("files", None)

        if submission:
            try:
                submission = Submission.objects.get(id=submission)
            except:
                raise serializers.ValidationError("Not a valid submission.")
            if not isStaffOfSub(user, submission):
                return returnForbidden()

        x = Run.delay(
            user=str(request.user),
            environmentID=assignment.environment.id,
            type=json.dumps(RunType.TestCase),
            pk=testCase.id,
            subID=submission.id if submission else None,
            fileOverrides=files,
            run_by_role="instructor",
        )
        return Response({"task": x.task_id})
