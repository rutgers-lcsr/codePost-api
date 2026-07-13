# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Admin actions for Docker image lifecycle management.

Provides API endpoints for:
- Rollback to previous version
- Cleanup old images
- Convert to manual configuration
"""
import logging
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from core.models import Environment
from core.permissions.capabilities import require_capability
from autograder.serializers.environment_actions import (
    EnvironmentRollbackRequestSerializer,
    EnvironmentRollbackResponseSerializer,
    EnvironmentCleanupRequestSerializer,
    EnvironmentCleanupResponseSerializer,
    EnvironmentConvertToManualRequestSerializer,
    EnvironmentConvertToManualResponseSerializer,
    EnvironmentStatusResponseSerializer,
)

logger = logging.getLogger(__name__)


class EnvironmentRollback(APIView):
    """
    Rollback environment to a previous image version.
    
    POST /autograder/environments/<id>/rollback/
    Body: {"version": 2}  (optional, defaults to previous version)
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        request=EnvironmentRollbackRequestSerializer,
        responses={200: EnvironmentRollbackResponseSerializer}
    )
    def post(self, request, environment_id):
        # Permission check
        try:
            env = Environment.objects.get(pk=environment_id)
        except Environment.DoesNotExist:
            return JsonResponse({"error": "Environment not found"}, status=404)
        
        require_capability(request.user, 'manage_test_cases', env.assignment)
        
        # Get target version
        target_version = request.data.get('version')
        if not target_version:
            # Default to previous version
            history = env.image_history or []
            if len(history) < 2:
                return JsonResponse({"error": "No previous version available"}, status=400)
            target_version = history[-2]["version"]
        
        from autograder.services.image_manager import ImageManager
        success = ImageManager.rollback_to_version(environment_id, target_version)
        
        if success:
            logger.info(f"Admin {request.user} rolled back env {environment_id} to v{target_version}")
            data = {
                "success": True,
                "message": f"Rolled back to version {target_version}",
                "version": target_version,
            }
            resp_ser = EnvironmentRollbackResponseSerializer(instance=data)
            return JsonResponse(resp_ser.data)
        else:
            return JsonResponse({"error": "Rollback failed"}, status=500)


class EnvironmentCleanup(APIView):
    """
    Cleanup old Docker images for environment.
    
    POST /autograder/environments/<id>/cleanup/
    Body: {"keep_count": 2}  (optional, defaults to 3)
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        request=EnvironmentCleanupRequestSerializer,
        responses={200: EnvironmentCleanupResponseSerializer}
    )
    def post(self, request, environment_id):
        try:
            env = Environment.objects.get(pk=environment_id)
        except Environment.DoesNotExist:
            return JsonResponse({"error": "Environment not found"}, status=404)
        
        require_capability(request.user, 'manage_test_cases', env.assignment)
        
        keep_count = request.data.get('keep_count', 3)
        
        from autograder.tasks import cleanup_images_task
        task = cleanup_images_task.delay(environment_id, keep_count)
        
        logger.info(f"Admin {request.user} triggered cleanup for env {environment_id}")
        data = {
            "success": True,
            "task_id": task.id,
            "message": f"Cleanup task dispatched",
        }
        resp_ser = EnvironmentCleanupResponseSerializer(instance=data)
        return JsonResponse(resp_ser.data)


class EnvironmentConvertToManual(APIView):
    """
    Convert auto-detect environment to manual configuration.
    
    POST /autograder/environments/<id>/convert-to-manual/
    Body: {"from_version": 2}  (optional, uses current if not specified)
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        request=EnvironmentConvertToManualRequestSerializer,
        responses={200: EnvironmentConvertToManualResponseSerializer}
    )
    def post(self, request, environment_id):
        try:
            env = Environment.objects.get(pk=environment_id)
        except Environment.DoesNotExist:
            return JsonResponse({"error": "Environment not found"}, status=404)
        
        require_capability(request.user, 'manage_test_cases', env.assignment)
        
        from_version = request.data.get('from_version')
        
        from autograder.services.image_manager import ImageManager
        success = ImageManager.convert_to_manual(environment_id, from_version)
        
        if success:
            logger.info(f"Admin {request.user} converted env {environment_id} to manual config")
            data = {
                "success": True,
                "message": "Environment converted to manual configuration",
            }
            resp_ser = EnvironmentConvertToManualResponseSerializer(instance=data)
            return JsonResponse(resp_ser.data)
        else:
            return JsonResponse({"error": "Conversion failed"}, status=500)


class EnvironmentStatus(APIView):
    """
    Get detailed environment status including version history.
    
    GET /autograder/environments/<id>/status/
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(responses={200: EnvironmentStatusResponseSerializer})
    def get(self, request, environment_id):
        try:
            env = Environment.objects.get(pk=environment_id)
        except Environment.DoesNotExist:
            return JsonResponse({"error": "Environment not found"}, status=404)
        
        require_capability(request.user, 'manage_test_cases', env.assignment)
        
        from autograder.services.image_manager import ImageManager
        status_data = ImageManager.get_current_status(environment_id)

        resp_ser = EnvironmentStatusResponseSerializer(instance=status_data)
        return JsonResponse(resp_ser.data)

