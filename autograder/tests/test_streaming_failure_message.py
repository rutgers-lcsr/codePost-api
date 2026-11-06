# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
A failed run streams an SSE "error" event carrying the executor's own message
(ExecutionResult.err). It used to format ExecutionResult.error, which is the classmethod,
so the user saw "<bound method ExecutionResult.error ...>".
"""
from unittest import mock

from django.test import TestCase

from autograder.services.executors.base import ExecutionResult
from autograder.services.executors.mock_file import MockFile
from autograder.services.executors.python import PythonExecutor
from core.models import Environment, User
from core.tests.factories import AssignmentFactory

FAILURE = "Docker image is not available"


class StreamingFailureMessageTests(TestCase):
    def test_executor_streaming_reports_the_failure_message(self):
        executor = PythonExecutor(MockFile(data="x = 1\n", name="s.py", extension=".py"))
        with mock.patch.object(executor, "execute", return_value=ExecutionResult.error(FAILURE)), \
                mock.patch.object(ExecutionResult, "save_cache"):
            out = "".join(executor.execute_streaming(user=None))
        self.assertIn(FAILURE, out)
        self.assertNotIn("bound method", out)

    def test_streaming_task_reports_the_failure_message(self):
        from autograder import tasks
        assignment = AssignmentFactory()
        Environment.objects.filter(assignment=assignment).delete()
        Environment.objects.create(assignment=assignment, language="python-3.12")
        file = assignment.submissions.first().files.first()
        user = User.objects.create_user(username="f@rutgers.edu", email="f@rutgers.edu", password="TestPass1!")
        executor = mock.Mock()
        executor.execute.return_value = ExecutionResult.error(FAILURE)
        redis_client = mock.Mock()
        with mock.patch.object(tasks, "_get_redis_client", return_value=redis_client), \
                mock.patch.object(tasks.Executor, "factory", return_value=executor):
            tasks.run_file_streaming_task("chan", file.id, user.id)
        published = " ".join(call.args[1] for call in redis_client.publish.call_args_list)
        self.assertIn(FAILURE, published)
        self.assertNotIn("bound method", published)
