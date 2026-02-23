# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Streaming executor view with Server-Sent Events (SSE) support

This module provides streaming execution endpoints that send progress updates
to the client using Server-Sent Events, preventing timeout issues with long-running
notebook executions.
"""

import json
import logging
import os
import time
import threading
from typing import Generator, Optional

from django.http import StreamingHttpResponse, JsonResponse
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from drf_spectacular.utils import extend_schema, OpenApiResponse

from autograder.services.executors import  ExecutionResult, Executor
from autograder.serializers.execution import FileExecutionRequestSerializer
from core.models import File, Submission, SubmissionFile, AssignmentFile, CourseFile, Assignment, Course, User
from core.permissions.helpers import isAuthenticated, isStaffOfSub, returnNotAuthorized, returnForbidden, isCourseAdmin
from core.permissions.permissions import FileExecutionPermissions

logger = logging.getLogger(__name__)


# Rate limiting for streaming execution
class StreamingExecutionRateThrottle(UserRateThrottle):
    """
    Rate limit for streaming execution endpoint.
    
    Same as regular execution to prevent resource abuse:
    - 5 requests per minute per user
    """
    rate = '30/min'


class ExecuteFileStreaming(GenericAPIView):
    """
    Execute a file (code or notebook) with streaming progress updates via SSE
    
    This endpoint streams execution progress to prevent timeout issues with
    long-running executions. The client receives updates as the execution progresses.
    
    Permissions:
    - Students: Can execute their own submission files
    - Graders/TAs: Can execute any file in courses they're staff for
    - Admins: Can execute any file in courses they admin
    - Superusers: Can execute any file
    
    Uses FileExecutionPermissions which delegates to appropriate permission class
    based on file type (SubmissionFile, AssignmentFile, CourseFile)
    
    POST /autograder/execute/file/streaming/
    Body: {
        "file_id": <int>,
        "timeout": <int, optional>,
        "force_execution": <bool, optional>
    }
    
    Response: Server-Sent Events stream with messages:
    - event: progress - Execution progress updates
    - event: complete - Final result with executed cells
    - event: error - Error information
    """
    
    permission_classes = [IsAuthenticated]
    throttle_classes = [StreamingExecutionRateThrottle]
    serializer_class = FileExecutionRequestSerializer
    
    @extend_schema(
        request=FileExecutionRequestSerializer,
        responses={
            200: OpenApiResponse(description='Server-Sent Events stream with ExecutionResult data'),
        }
    )
    def post(self, request):
        """Handle streaming execution request"""
        
        # Validate through serializer (handles camelCase → snake_case mapping)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        
        file_id = validated["file_id"]
        
        # Check file permissions here instead of in the _execute_with_streaming method
        file_obj, submission, assignment, _ = File.get_file_obj(file_id)
        
        file_permissions = FileExecutionPermissions()
        if not file_permissions.has_object_permission(request, self, file_obj):
            logger.warning(f"[ExecuteFileStreaming] Permission denied for user {request.user.id} on file {file_id}")
            return JsonResponse(
                {"error": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        logger.info(f"[ExecuteFileStreaming] Starting streaming execution for file {file_id} by user {request.user.id}, submission={submission.id if submission else 'N/A'}, assignment={assignment.id if assignment else 'N/A'}")
        
        # Start streaming response
        response = StreamingHttpResponse(
            self._execute_with_streaming(request, file_obj, submission, assignment, validated),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
        
        return response
    
    def _execute_with_streaming(self, request, file_obj: File | SubmissionFile | AssignmentFile | CourseFile, submission: Submission | None, assignment: Assignment | None, data: dict) -> Generator[str, None, None]:
        """
        Generator that yields SSE messages during execution, 
        Assumes that the file has already been checked for permissions.
        
        Args:
            request: Django request object
            file_obj: File object to execute
            submission: Submission object
            assignment: Assignment object
            data: Request data with execution parameters
            
        Yields:
            SSE formatted messages
        """
        try:
            # Send initial progress
            yield self._sse_message("progress", {"status": "starting", "message": "Fetching file..."})
        
            
            user = request.user
            
            # If user is a student and not a staff member, they cannot force execute
            if  submission and not isStaffOfSub(user, submission):
                force_execute = False
                test_code = None
                code_override = None
            else:
                force_execute = data.get("force_execute", False)
                test_code = data.get("test_code")
                code_override = data.get("code_override")
                
            if test_code or code_override:
                force_execute = True

                # Permission check for override
                if not assignment:
                     _, assignment, _ = file_obj.get_file_info()
                
                if assignment:
                      if not user.is_superuser and not isCourseAdmin(user, assignment.course):
                           if not assignment.gradersCanEditSubmissions:
                                yield self._sse_message("error", {"error": "Permission denied: Graders cannot edit submissions for this assignment."})
                                return

            logger.info(f"[ExecuteFileStreaming] Checking cache for file {file_obj.id}, force_execute={force_execute}")
            
            if not force_execute:
                # Check for cached execution result
                from core.models import CachedExecutionResult
                cached_result = CachedExecutionResult.get_cached_result(file_obj)
                
                if cached_result:
                    # Return cached result
                    logger.info(f"[ExecuteFileStreaming] Cache HIT for file {file_obj.id}, returning cached result")
                    yield self._sse_message("progress", {"status": "cached", "message": "Using cached execution result"})
                    
                    response_data = cached_result.get_cached_formated_response(file_obj)
                    yield self._sse_message("complete", response_data)
                    return
            
            
            logger.info(f"[ExecuteFileStreaming] Cache MISS for file {file_obj.id}, executing...")

            # If student (and not staff), they cannot execute new code - only view cache
            if submission and not isStaffOfSub(user, submission):
                logger.warning(f"[ExecuteFileStreaming] Student {user.id} attempted to execute file {file_obj.id} without cache")
                yield self._sse_message("error", {"error": "No cached execution result available."})
                return
            
            yield self._sse_message("progress", {"status": "fetching", "message": "Loading file content..."})
            
            # Determine file type
            file_name = file_obj.name.lower() if file_obj.name else ""
            timeout:int = data.get("timeout", 30)
            if timeout > 120 or timeout <= 0:
                # Force maximum timeout of 120 seconds
                timeout = 120
            
            # Check if it's a notebook
            try:
                executor = Executor.factory(file_obj, content_override=code_override, test_code=test_code)
                if not executor:
                    yield self._sse_message("error", {
                        "error": f"No executor found for language: {file_name}"
                    })
                    return
                # Execute code
                yield from executor.execute_streaming(request.user)
            except GeneratorExit:
                # Client disconnected - this is normal
                logger.info("[ExecuteFileStreaming] Client disconnected")
                raise
            except Exception as e:
                logger.error(f"[ExecuteFileStreaming] Error in sub-generator: {e}", exc_info=True)
                yield self._sse_message("error", {"error": f"Execution error: {str(e)}"})
                
        except GeneratorExit:
            # Client disconnected - this is normal
            logger.info("[ExecuteFileStreaming] Client disconnected")
            raise
        except Exception as e:
            logger.error(f"[ExecuteFileStreaming] Unexpected error: {e}", exc_info=True)
            yield self._sse_message("error", {"error": f"Execution error: {str(e)}"})
    
    
    
    def _sse_message(self, event: str, data: dict) -> str:
        """
        Format a Server-Sent Event message
        
        Args:
            event: Event type (progress, complete, error)
            data: Event data as dictionary
            
        Returns:
            Formatted SSE message string
        """
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"
