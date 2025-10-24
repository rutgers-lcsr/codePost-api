"""
Execution API Views

Provides REST API endpoints for executing code and notebooks
"""

import logging
from typing import Any, cast

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle
from autograder.services.executor import Executor
from core.models import File
from core.permissions.helpers import returnForbidden

logger = logging.getLogger(__name__)


# Rate limiting classes for execution endpoints
class ExecutionRateThrottle(UserRateThrottle):
    """
    Rate limit for code execution endpoints.
    
    Limits to prevent resource abuse:
    - 5 requests per minute per user
    - Applies to all execution endpoints
    """
    rate = '5/min'


class CodeExecutionSerializer(serializers.Serializer):
    """Serializer for code execution requests"""

    code = serializers.CharField(required=True)
    language = serializers.CharField(required=True)
    timeout = serializers.IntegerField(required=False, default=30)
    working_dir = serializers.CharField(required=False, allow_null=True)


class NotebookExecutionSerializer(serializers.Serializer):
    """Serializer for notebook execution requests"""

    notebook_content = serializers.CharField(required=True)
    timeout = serializers.IntegerField(required=False, default=60)
    kernel_name = serializers.CharField(required=False, default="python3")


class NotebookCellExecutionSerializer(serializers.Serializer):
    """Serializer for single cell execution requests"""

    cell_code = serializers.CharField(required=True)
    cell_index = serializers.IntegerField(required=False, default=0)
    timeout = serializers.IntegerField(required=False, default=30)
    kernel_name = serializers.CharField(required=False, default="python3")


class FileExecutionSerializer(serializers.Serializer):
    """Serializer for file execution requests"""

    file_id = serializers.IntegerField(required=True)
    timeout = serializers.IntegerField(required=False, default=30)


class ExecuteFileView(APIView):
    """
    Execute a codePost file - use stream execution instead. 
    
    Permissions:
    - Codepost staff only: Superusers can execute any file
    
    Uses FilePermissions which delegates to appropriate permission class
    based on file type (SubmissionFile, AssignmentFile, CourseFile)

    POST /autograder/execute/file/
    {
        "file_id": 123,
        "timeout": 30
    }
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ExecutionRateThrottle]

    def post(self, request):
        # Restrict to superusers only
        if not request.user.is_superuser:
            return returnForbidden()
        
        
        serializer = FileExecutionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = cast(dict[str, Any], serializer.validated_data)
        file_id = data["file_id"]
        timeout = data.get("timeout", 30)

        file,_,_,_ = File.get_file_obj(file_id)

        executor = Executor.factory(file)
        if not executor:
            return Response(
                {"error": "File type not executable"},
                status=status.HTTP_400_BAD_REQUEST
            )

        executor.DEFAULT_TIMEOUT = timeout

        execution_result = executor.execute()
        return Response(execution_result.to_dict(), status=status.HTTP_200_OK)


