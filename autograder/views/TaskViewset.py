# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django_celery_results.models import TaskResult
from drf_spectacular.utils import extend_schema
import json
import logging
import re

from celery.result import AsyncResult
from autograder.serializers.execution import TaskStatusResponseSerializer
from core.models import Environment, File, Submission
from core.permissions.helpers import isCourseStaff

logger = logging.getLogger(__name__)

# Task name -> course of the object the task's first positional argument names. The result
# backend stores each task's name and argument reprs (CELERY_RESULT_EXTENDED); that is all
# the ownership information there is, so it is what access is derived from.
_TASK_COURSE = {
    'autograder.tasks.run_file_task': lambda pk: File.objects.get(pk=pk).get_file_info()[2],
    'autograder.tasks.run_test_task': lambda pk: Submission.objects.get(pk=pk).assignment.course,
    'autograder.tasks.cleanup_images_task': lambda pk: Environment.objects.get(pk=pk).assignment.course,
    'autograder.run.BuildEnvironment': lambda pk: Environment.objects.get(pk=pk).assignment.course,
    'autograder.run.RunAll': lambda pk: Environment.objects.get(pk=pk).assignment.course,
}

# Index of the dispatching user's id among the positional arguments (run_test_task passes
# it as the user_id keyword instead).
_POSITIONAL_USER_INDEX = {'autograder.tasks.run_file_task': 1, 'autograder.run.RunAll': 1}


def _stored_repr(raw) -> str:
    """The backend stores argsrepr/kwargsrepr JSON-encoded."""
    try:
        value = json.loads(raw) if raw else ''
    except ValueError:
        return ''
    return value if isinstance(value, str) else ''


def _leading_ints(args_repr: str) -> list[int]:
    """Ids at the front of a positional-args repr such as "(12, 5, False)". Celery truncates
    long reprs, so only the leading integers are trusted."""
    ints: list[int] = []
    for part in args_repr.strip().lstrip('([').split(','):
        part = part.strip()
        if not re.fullmatch(r'\d+', part):
            break
        ints.append(int(part))
    return ints


def _may_read_task(user, task_result) -> bool:
    """Superusers, the user who dispatched the task, and staff of the course it ran in."""
    if user.is_superuser:
        return True
    name = task_result.task_name
    course_of = _TASK_COURSE.get(name)
    ids = _leading_ints(_stored_repr(task_result.task_args))
    if course_of is None or not ids:
        return False

    index = _POSITIONAL_USER_INDEX.get(name)
    if index is not None and len(ids) > index:
        dispatcher = ids[index]
    else:
        found = re.search(r"'user_id': (\d+)", _stored_repr(task_result.task_kwargs))
        dispatcher = int(found.group(1)) if found else None
    if dispatcher == user.id:
        return True

    try:
        course = course_of(ids[0])
    except (File.DoesNotExist, Submission.DoesNotExist, Environment.DoesNotExist):
        return False
    return course is not None and isCourseStaff(user, course)


class TaskViewSet(viewsets.ViewSet):
    """
    A simple ViewSet for retrieving task results
    """

    @extend_schema(
        responses={200: TaskStatusResponseSerializer}
    )
    def retrieve(self, request, pk=None):
        # Results (execution and test output) belong to whoever dispatched the task and the
        # staff of its course. An id with no stored row yet has nothing to leak.
        stored = TaskResult.objects.filter(task_id=pk).first()
        if stored is not None and not _may_read_task(request.user, stored):
            raise PermissionDenied("You do not have access to this task.")

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

