from rest_framework import viewsets
from rest_framework.response import Response
from django_celery_results.models import TaskResult
import json

from celery.result import AsyncResult
from autograder.celery import app


class TaskViewSet(viewsets.ViewSet):
    """
    A simple ViewSet for retrieving task results
    """

    def retrieve(self, request, pk=None):
        res = AsyncResult(pk)
        if res.ready():
            res = TaskResult.objects.get(task_id=pk)
            result = res.result
            status = res.status
            if status == "SUCCESS" or status == "FAILURE":
                return Response({"status": status, "result": json.loads(result)})
            else:
                return Response({"status": status, "result": None})
        else:
            print(res.info)
            if res.info and "progress" in res.info:
                return Response({"status": res.state, "result": res.info["progress"]})
            else:
                return Response({"status": res.state, "result": None})
