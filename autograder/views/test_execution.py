# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from autograder.services.TestService import TestService
from autograder.serializers.execution import (
    TestExecutionRequestSerializer,
    TestExecutionResultSerializer,
)
from core.models import Submission, TestCase
from autograder.tasks import run_test_task

class RunTestView(GenericAPIView):
    """
    API access to the Modern Testing Architecture.
    Runs a specific TestCase against a Submission.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TestExecutionRequestSerializer

    @extend_schema(
        request=TestExecutionRequestSerializer,
        responses={200: TestExecutionResultSerializer}
    )
    def post(self, request):
        # Validate through serializer (handles camelCase → snake_case mapping)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        test_id = validated.get('testId')
        submission_id = validated['submissionId']

        # Validate Permissions (Basic check that user can access this submission)
        # TODO: Add robust permission checks (is Admin or Student owner)
        try:
             submission = Submission.objects.get(id=submission_id)
             submitter_is_staff = False
             try:
                 from core.permissions.helpers import isStaffOfSub
                 if isStaffOfSub(request.user, submission):
                    submitter_is_staff = True
             except ImportError:
                 # Fallback if helpers not available/circular import
                 pass

             # Strict Check: requester must be staff
             if not (request.user.is_staff or submitter_is_staff):
                  return Response(
                      {"error": "Permission denied"}, 
                      status=status.HTTP_403_FORBIDDEN
                  )
        except Submission.DoesNotExist:
             return Response({"error": "Submission not found"}, status=status.HTTP_404_NOT_FOUND)

        # Run Test(s) - file_overrides already normalized by serializer
        file_overrides = validated.get('file_overrides')
        
        # Convert keys to int if they are strings (JSON dict keys are always strings)
        if file_overrides:
             try:
                 file_overrides = {int(k): v for k, v in file_overrides.items()}
             except ValueError:
                 return Response({"error": "Invalid file_overrides keys, must be integer file IDs"}, status=status.HTTP_400_BAD_REQUEST)

        if test_id:
            task = run_test_task.delay(submission_id, test_id=test_id, user_id=request.user.id, file_overrides=file_overrides)
        else:
            task = run_test_task.delay(submission_id, user_id=request.user.id, file_overrides=file_overrides)

        from autograder.serializers.execution import AsyncTaskResponseSerializer
        response_payload = {
            "task_id": task.id,
            "status": "queued",
        }
        response_serializer = AsyncTaskResponseSerializer(instance=response_payload)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
