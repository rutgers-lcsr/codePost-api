from core.models import TestCase
from core.serializers.testCase import TestCaseSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import TestCasePermissions
from core.models import Submission
from core.permissions.helpers import isStaffOfSub, returnNotAuthorized

from rest_framework.decorators import action
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

    @action(detail=True, methods=["POST"])
    def run(self, request, pk=None):
        user = self.request.user
        testCase = TestCase.objects.get(id=pk)
        assignment = testCase.testCategory.assignment
        course = assignment.course

        if not isAuthenticated(user):
            return returnNotAuthorized()

        if not isCourseStaff(user, course):
            return returnForbidden()

        if not assignment.environment or not assignment.environment.language:
            raise serializers.ValidationError(
                "Environment has not been created for this asignment."
            )

        submission = self.request.data.get("submission", None)
        files = None

        if submission:
            files = self.request.data.get("files", None)

            if files != None:
                files = json.loads(files)

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
