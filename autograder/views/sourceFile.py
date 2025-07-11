from core.models import SourceFile, Submission
from autograder.serializers.sourceFile import SourceFileSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from autograder.permissions.permissions import SourceFilePermissions

from core.permissions.helpers import isCourseAdmin, isStaffOfSub
from core.permissions.helpers import isAuthenticated
from core.permissions.helpers import (
    returnNotAuthorized,
    returnForbidden,
    returnNotFound,
)

from rest_framework.response import Response

from autograder.run import Run, RunType

import json

from rest_framework import serializers

from rest_framework.decorators import action


class SourceFileViewSet(ListProtectedViewSet):
    """
    list:
    Return a list of all the testFiles.

    create:
    Create a new testFile.

    retrieve:
    Return the given testFile.

    update:
    Update a testFile.

    partial_update:
    Update a testFile.

    delete:
    Delete a testFile.
    """

    queryset = SourceFile.objects.all()
    serializer_class = SourceFileSerializer
    permission_classes = (IsAuthenticated, SourceFilePermissions)

    @action(detail=True, methods=["GET"])
    def run(self, request, pk=None):
        user = self.request.user
        sourceFile = SourceFile.objects.get(id=pk)
        assignment = sourceFile.environment.assignment
        course = assignment.course

        if not isAuthenticated(user):
            return returnNotAuthorized()

        if not isCourseAdmin(user, course):
            return returnForbidden()

        if not assignment.environment or not assignment.environment.language:
            raise serializers.ValidationError(
                "Environment has not been created for this asignment."
            )

        submission = self.request.query_params.get("submission", None)
        if submission:
            try:
                submission = Submission.objects.get(id=submission)
            except:
                raise serializers.ValidationError("Not a valid submission.")
            if not isStaffOfSub(user, submission):
                return returnForbidden()

        x = Run.delay(
            user=str(request.user),
            environmentID=sourceFile.environment.id,
            type=json.dumps(RunType.SourceFile),
            pk=sourceFile.id,
            subID=submission.id if submission else None,
            run_by_role="instructor",
        )
        return Response({"task": x.task_id})
