# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Execution API Views

Provides REST API endpoints for executing code and notebooks
"""

import logging
from typing import Any, cast, Optional
import json

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.generics import GenericAPIView
from rest_framework.throttling import UserRateThrottle
from drf_spectacular.utils import extend_schema
from autograder.services.executors import Executor
from autograder.services.executors.mock_file import MockFile
from autograder.serializers.execution import (
    FileExecutionRequestSerializer,
    ExecutionResultSerializer,
    CodeExecutionRequestSerializer,
    NotebookExecutionRequestSerializer,
    NotebookCellExecutionRequestSerializer,
)
from core.models import File
from core.permissions.helpers import returnForbidden, isGrader, isCourseAdmin

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


LANGUAGE_EXTENSION_MAP = {
    "python": ".py",
    "python-3.12": ".py",
    "python-3.11": ".py",
    "python-3.10": ".py",
    "python-3.7": ".py",
    "python-2.7": ".py",
    "java": ".java",
    "java-17": ".java",
    "java-11": ".java",
    "node": ".js",
    "node-20": ".js",
    "node-18": ".js",
    "javascript": ".js",
    "js": ".js",
    "c": ".c",
    "cpp": ".cpp",
    "c/c++": ".cpp",
    "r": ".r",
    "r-4": ".r",
    "ruby": ".rb",
    "php": ".php",
    "bash": ".sh",
    "sh": ".sh",
}


def _get_extension_for_language(language: Optional[str]) -> Optional[str]:
    if not language:
        return None
    return LANGUAGE_EXTENSION_MAP.get(language.lower())


class ExecuteFileView(GenericAPIView):
    """
    Execute a codePost file - use stream execution instead. This endpoint is used for testing file execution.
    
    DEPRECATED: Use /autograder/async/execute/file/ instead.
    This view executes synchronously, blocking the request thread. It should not be used in production
    for long-running tasks.
    
    Permissions:
    - Codepost staff only: Superusers can execute any file
    - Course Staff: Can execute with overrides if allowed by assignment
    
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
    serializer_class = FileExecutionRequestSerializer

    @extend_schema(
        request=FileExecutionRequestSerializer,
        responses={200: ExecutionResultSerializer}
    )
    def post(self, request):
        serializer = FileExecutionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = cast(dict[str, Any], serializer.validated_data)
        file_id = data["file_id"]
        timeout = data.get("timeout", 30)
        test_code = data.get("test_code")
        code_override = data.get("code_override")

        try:
            file, _, assignment, _ = File.get_file_obj(file_id)
        except Exception:
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        # Permission Check
        if not assignment:
            return Response({"error": "No assignment found for file"}, status=status.HTTP_404_NOT_FOUND)

        if code_override:
            # If overriding code, check if user has edit permissions
            allowed = False
            if request.user.is_superuser:
                allowed = True
            elif isCourseAdmin(request.user, assignment.course):
                allowed = True
            elif isGrader(request.user, assignment.course):
                if assignment and assignment.gradersCanEditSubmissions:
                    allowed = True
            
            if not allowed:
                return returnForbidden()
        else:
            # Default behavior (disk execution) restricted to superusers for now
            if not request.user.is_superuser:
                return returnForbidden()

        executor = Executor.factory(file, content_override=code_override, test_code=test_code)
        if not executor:
            return Response(
                {"error": "File type not executable"},
                status=status.HTTP_400_BAD_REQUEST
            )

        executor.DEFAULT_TIMEOUT = timeout

        execution_result = executor.execute()
        response_serializer = ExecutionResultSerializer(instance=execution_result.to_dict())
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class ExecuteCodeView(GenericAPIView):
    """
    Execute a code snippet using the autograder executors.
    
    DEPRECATED: Use async endpoints.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ExecutionRateThrottle]
    serializer_class = CodeExecutionRequestSerializer

    @extend_schema(
        request=CodeExecutionRequestSerializer,
        responses={200: ExecutionResultSerializer}
    )
    def post(self, request):
        serializer = CodeExecutionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)

        language = data.get("language")

        
        extension = _get_extension_for_language(language)
        if not extension:
            return Response({"error": "Unsupported language"}, status=status.HTTP_400_BAD_REQUEST)

        code = data.get("code", "")
        timeout = data.get("timeout", 30)

        mock_file = MockFile(code, f"snippet{extension}", extension=extension)
        executor = Executor.factory(mock_file)
        if not executor:
            return Response({"error": "Unsupported language"}, status=status.HTTP_400_BAD_REQUEST)

        executor.DEFAULT_TIMEOUT = timeout
        execution_result = executor.execute()
        response_serializer = ExecutionResultSerializer(instance=execution_result.to_dict())
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class ExecuteNotebookView(GenericAPIView):
    """
    Execute a full notebook payload.
    
    DEPRECATED: Use async endpoints.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ExecutionRateThrottle]
    serializer_class = NotebookExecutionRequestSerializer

    @extend_schema(
        request=NotebookExecutionRequestSerializer,
        responses={200: ExecutionResultSerializer}
    )
    def post(self, request):
        serializer = NotebookExecutionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)

        notebook_content = data.get("notebook_content", "")
        kernel_name = data.get("kernel_name", None)
        timeout = data.get("timeout", 60)

        if kernel_name:
            try:
                nb = json.loads(notebook_content)
                metadata = nb.setdefault("metadata", {})
                metadata.setdefault("kernelspec", {"name": kernel_name, "display_name": kernel_name})
                notebook_content = json.dumps(nb)
            except Exception:
                pass

        mock_file = MockFile(notebook_content, "notebook.ipynb", extension=".ipynb")
        executor = Executor.factory(mock_file)
        if not executor:
            return Response({"error": "Unsupported notebook kernel"}, status=status.HTTP_400_BAD_REQUEST)

        executor.DEFAULT_TIMEOUT = timeout
        execution_result = executor.execute()
        response_serializer = ExecutionResultSerializer(instance=execution_result.to_dict())
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class ExecuteNotebookCellView(GenericAPIView):
    """Execute a single notebook cell by wrapping it in a minimal notebook."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ExecutionRateThrottle]
    serializer_class = NotebookCellExecutionRequestSerializer

    @extend_schema(
        request=NotebookCellExecutionRequestSerializer,
        responses={200: ExecutionResultSerializer}
    )
    def post(self, request):
        serializer = NotebookCellExecutionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)

        cell_code = data.get("cell_code", "")
        kernel_name = data.get("kernel_name", "python3")
        timeout = data.get("timeout", 30)

        notebook_payload = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": cell_code,
                }
            ],
            "metadata": {"kernelspec": {"name": kernel_name, "display_name": kernel_name}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }

        notebook_content = json.dumps(notebook_payload)
        mock_file = MockFile(notebook_content, "cell.ipynb", extension=".ipynb")
        executor = Executor.factory(mock_file)
        if not executor:
            return Response({"error": "Unsupported notebook kernel"}, status=status.HTTP_400_BAD_REQUEST)

        executor.DEFAULT_TIMEOUT = timeout
        execution_result = executor.execute()
        response_serializer = ExecutionResultSerializer(instance=execution_result.to_dict())
        return Response(response_serializer.data, status=status.HTTP_200_OK)

