from rest_framework.views import APIView
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

class RunTestView(APIView):
    """
    API access to the Modern Testing Architecture.
    Runs a specific TestCase against a Submission.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=TestExecutionRequestSerializer,
        responses={200: TestExecutionResultSerializer}
    )
    def post(self, request):
        test_id = request.data.get('testId')
        submission_id = request.data.get('submissionId')

        if not test_id or not submission_id:
            return Response(
                {"error": "Missing testId or submissionId"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

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

        # Run Test
        result = TestService.run_test(test_id, submission_id, user_id=request.user.id)
        
        if result['success']:
            return Response(result)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
