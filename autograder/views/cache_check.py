"""
API endpoint to check if execution cache exists for a file
"""

import logging
from django.http import JsonResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle

from core.models import File, SubmissionFile, AssignmentFile, CourseFile, CachedExecutionResult
from core.permissions.helpers import isAuthenticated, returnNotAuthorized, returnForbidden
from core.permissions.permissions import FileExecutionPermissions

logger = logging.getLogger(__name__)


# Rate limiting for cache check endpoint
class CacheCheckRateThrottle(UserRateThrottle):
    """
    Rate limit for cache check endpoint.
    
    Higher limit than execution since checking cache is lightweight.
    - 60 requests per minute per user
    """
    rate = '60/min'


class CheckExecutionCache(APIView):
    """
    Check if execution cache exists for a file
    
    Permissions:
    - Students: Can check cache for their own submission files
    - Graders/TAs: Can check cache for any file in courses they're staff for
    - Admins: Can check cache for any file in courses they admin
    - Superusers: Can check cache for any file
    
    Uses FilePermissions which delegates to appropriate permission class
    based on file type (SubmissionFile, AssignmentFile, CourseFile)
    
    GET /autograder/execute/file/cache/check/?file_id=<int>
    
    Response: {
        "has_cache": true/false,
        "executed_at": "ISO timestamp" (if has_cache),
        "executed_by": "username" (if has_cache),
        "execution_time": 12.5 (if has_cache)
    }
    """
    
    permission_classes = [IsAuthenticated]
    throttle_classes = [CacheCheckRateThrottle]
    
    def get(self, request):
        """Check if cache exists for file"""
        
        logger.info(f"[CheckExecutionCache] Request from user: {request.user}, authenticated: {request.user.is_authenticated}")
        
        # Get file_id from query params
        file_id = request.GET.get("file_id")
        logger.info(f"[CheckExecutionCache] Checking cache for file_id: {file_id}")
        
        if not file_id:
            return JsonResponse(
                {"error": "file_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            file_id = int(file_id)
        except ValueError:
            return JsonResponse(
                {"error": "file_id must be an integer"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file_obj, _, _, _ = File.get_file_obj(file_id)
        
        
        # File not found in any table
        if not file_obj:
            return JsonResponse(
                {"error": "File not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        
        # Check permissions using FileExecutionPermissions class
        file_permissions = FileExecutionPermissions()
        if not file_permissions.has_object_permission(request, self, file_obj):
            logger.warning(f"[CheckExecutionCache] Permission denied for user {request.user.id} on file {file_obj.id}")
            return JsonResponse(
                {"error": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check for cached result
        cached_result = CachedExecutionResult.get_cached_result(file_obj)
        
        if cached_result:
            logger.info(f"[CheckExecutionCache] Cache found for file {file_id}")
            return JsonResponse({
                "has_cache": True,
                "executed_at": cached_result.executed_at.isoformat(),
                "executed_by": cached_result.executed_by.username if cached_result.executed_by else None,
                "execution_time": cached_result.execution_time_seconds
            })
        else:
            logger.info(f"[CheckExecutionCache] No cache found for file {file_id}")
            return JsonResponse({
                "has_cache": False
            })
