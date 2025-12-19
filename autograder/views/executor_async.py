from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import logging

from core.models import File
from core.permissions.permissions import FileExecutionPermissions
from core.permissions.helpers import isStaffOfSub
from autograder.tasks import run_file_task

logger = logging.getLogger(__name__)

class ExecuteFileAsyncView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        file_id = request.data.get("file_id")
        timeout = request.data.get("timeout", 30)
        force_execute = request.data.get("force_execute", False)
        
        if not file_id:
             return Response({"error": "file_id required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
             # Check permissions
             file_obj, submission, _, _ = File.get_file_obj(file_id)
        except Exception:
             return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        perm = FileExecutionPermissions()
        if not perm.has_object_permission(request, self, file_obj):
             return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
             
        # Enforce force_execute permissions (Staff only)
        if submission and not isStaffOfSub(request.user, submission):
             force_execute = False

        # Dispatch Task
        task = run_file_task.delay(file_id, request.user.id, timeout, force_execute)
        
        return Response({
             "task_id": task.id,
             "status": "queued"
        })
