from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import logging
from drf_spectacular.utils import extend_schema

from core.models import File, CachedExecutionResult
from core.permissions.permissions import FileExecutionPermissions
from core.permissions.helpers import isStaffOfSub, isCourseStaff
from autograder.tasks import run_file_task
from autograder.serializers.execution import (
    AsyncExecutionRequestSerializer,
    AsyncTaskResponseSerializer,
)

logger = logging.getLogger(__name__)


class ExecuteFileAsyncView(APIView):
    """
    Async file execution endpoint.
    
    Permissions:
    - Staff: Can execute freely, including force_execute
    - Students: Can only retrieve cached results (cache must exist)
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        request=AsyncExecutionRequestSerializer,
        responses={200: AsyncTaskResponseSerializer}
    )
    def post(self, request):
        file_id = request.data.get("file_id")
        timeout = request.data.get("timeout", 30)
        force_execute = request.data.get("force_execute", False)
        test_code = request.data.get("test_code", None)
        example_code = request.data.get("example_code", None)  # For testing against filled-out templates
        
        if not file_id:
            return Response(
                {"error": "file_id required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            file_obj, submission, _, _ = File.get_file_obj(file_id)
        except Exception:
            return Response(
                {"error": "File not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Check base file execution permissions
        perm = FileExecutionPermissions()
        if not perm.has_object_permission(request, self, file_obj):
            return Response(
                {"error": "Forbidden"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Determine if user is staff of the submission or the assignment/course
        is_staff = False
        if submission:
            is_staff = isStaffOfSub(request.user, submission)
        else:
            # For AssignmentFiles (Solution Code), check if user is course staff
            _, assignment, course = file_obj.get_file_info()
            if course:
                is_staff = isCourseStaff(request.user, course)
        
        # Students cannot force execute and must have cached result
        if not is_staff:
            # Since this is a student, setting force_execute to False will prevent them from 
            # triggering a new execution if the cached result does not exist.
            force_execute = False
            # Students also cannot inject test code or example code
            test_code = None
            example_code = None
            
            if not CachedExecutionResult.get_cached_result(file_obj):
                return Response(
                    {"error": "No cached result available. Students cannot trigger new execution."}, 
                    status=status.HTTP_403_FORBIDDEN
                )

        # Dispatch task
        task = run_file_task.delay(
            file_id, request.user.id, timeout, force_execute, 
            test_code=test_code, example_code=example_code
        )
        
        return Response({
            "task_id": task.id,
            "status": "queued"
        })
