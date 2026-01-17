from rest_framework import viewsets
from rest_framework.response import Response
from django_celery_results.models import TaskResult
from drf_spectacular.utils import extend_schema
import json
import logging

from celery.result import AsyncResult
from autograder.celery import app
from autograder.serializers.execution import TaskStatusResponseSerializer

logger = logging.getLogger(__name__)


class TaskViewSet(viewsets.ViewSet):
    """
    A simple ViewSet for retrieving task results
    """

    @extend_schema(
        responses={200: TaskStatusResponseSerializer}
    )
    def retrieve(self, request, pk=None):
        res = AsyncResult(pk)
        
        # First check if AsyncResult shows ready
        if res.ready():
            try:
                task_result = TaskResult.objects.get(task_id=pk)
                result = task_result.result
                status = task_result.status
                if status == "SUCCESS" or status == "FAILURE":
                    return Response({"status": status, "result": json.loads(result)})
                else:
                    return Response({"status": status, "result": None})
            except TaskResult.DoesNotExist:
                # Task ready but result not in DB yet, return from AsyncResult
                return Response({
                    "status": res.state,
                    "result": res.result if res.result else None
                })
        
        # AsyncResult not ready - check database directly (might be faster than broker)
        try:
            task_result = TaskResult.objects.get(task_id=pk)
            status = task_result.status
            if status in ("SUCCESS", "FAILURE"):
                return Response({"status": status, "result": json.loads(task_result.result)})
        except TaskResult.DoesNotExist:
            pass
        
        # Still pending
        if res.info and isinstance(res.info, dict) and "progress" in res.info:
            return Response({"status": res.state, "result": res.info["progress"]})
        else:
            return Response({"status": res.state, "result": None})

