# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import logging
from drf_spectacular.utils import extend_schema

from core.models import File, CachedExecutionResult
from core.permissions.permissions import FileExecutionPermissions
from core.permissions.helpers import isStaffOfSub, isCourseStaff, isCourseAdmin, returnForbidden
from autograder.tasks import run_file_task
from autograder.serializers.execution import (
    AsyncExecutionRequestSerializer,
    AsyncTaskResponseSerializer,
)

logger = logging.getLogger(__name__)


class ExecuteFileAsyncView(GenericAPIView):
    """
    Async file execution endpoint.
    
    Permissions:
    - Staff: Can execute freely, including force_execute
    - Students: Can only retrieve cached results (cache must exist)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = AsyncExecutionRequestSerializer
    
    @extend_schema(
        request=AsyncExecutionRequestSerializer,
        responses={200: AsyncTaskResponseSerializer}
    )
    def post(self, request):
        # Validate through serializer (handles camelCase → snake_case mapping)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        file_id = validated["file_id"]
        timeout = validated.get("timeout", 30)
        force_execute = validated.get("force_execute", False)
        test_code = validated.get("test_code")
        example_code = validated.get("example_code")
        code_override = validated.get("code_override")

        # If code_override is present, force execution (bypass cache)
        if code_override:
            force_execute = True

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
        assignment = None
        if submission:
            is_staff = isStaffOfSub(request.user, submission)
            assignment = submission.assignment
        else:
            # For AssignmentFiles (Solution Code), check if user is course staff
            _, assignment, course = file_obj.get_file_info()
            if course:
                is_staff = isCourseStaff(request.user, course)
        
        # Check permission for code overrides (editing submissions)
        if is_staff and code_override and assignment:
            if not request.user.is_superuser and not isCourseAdmin(request.user, assignment.course):
                if assignment.gradersCanEditSubmissions is not None and not assignment.gradersCanEditSubmissions:
                    return returnForbidden()
        
        # Students cannot force execute and must have cached result
        if not is_staff:
            # Since this is a student, setting force_execute to False will prevent them from 
            # triggering a new execution if the cached result does not exist.
            force_execute = False
            # Students also cannot inject test code, example code, or override content
            test_code = None
            example_code = None
            code_override = None
            
            if not CachedExecutionResult.get_cached_result(file_obj):
                return Response(
                    {"error": "No cached result available. Students cannot trigger new execution."}, 
                    status=status.HTTP_403_FORBIDDEN
                )

        # Dispatch task
        task = run_file_task.delay(  # type: ignore[operator]  # celery .delay() untyped
            file_id, request.user.id, timeout, force_execute, 
            test_code=test_code, example_code=example_code, code_override=code_override
        )

        response_payload = {
            "task_id": task.id,
            "status": "queued",
        }
        response_serializer = AsyncTaskResponseSerializer(instance=response_payload)
        return Response(response_serializer.data)
