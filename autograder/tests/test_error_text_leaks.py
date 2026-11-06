# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Raw text of an unexpected exception must not reach anything a user can see (task results,
SSE frames, websocket messages, run results, build logs, student-visible result files).
Every test raises with MARKER, which stands for a path or connection string, and asserts
it is gone; the expected-domain diagnostics instructors rely on are asserted to survive.
"""
import asyncio
import json
from unittest import mock

import docker
import factory
from django.db.models.signals import post_save
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APITestCase

from autograder.services.executors import base as base_module
from autograder.services.executors.base import Executor, ExecutionResult
from autograder.services.executors.cpp import CPPExecutor
from autograder.services.executors.java import JavaExecutor, JavaNotebookExecutor
from autograder.services.executors.mock_file import MockFile
from autograder.services.executors.node import NodeExecutor, NodeNotebookExecutor
from autograder.services.executors.php import PHPExecutor, PHPNotebookExecutor
from autograder.services.executors.python import PythonExecutor, PythonNotebookExecutor
from autograder.services.executors.r import RExecutor, RNotebookExecutor
from autograder.services.executors.ruby import RubyExecutor, RubyNotebookExecutor
from autograder.services.safe_errors import RunUnavailable, safe_error_text
from autograder.tests.test_executor_runner_staging import _mock_file, _notebook_file
from core.models import AutograderExecutionEvent, Environment, SubmissionVariantRun, User
from core.tests.factories import AssignmentFactory, CourseFactory

MARKER = "SECRET-/srv/internal/path"


class SafeErrorTextTests(SimpleTestCase):
    def test_unexpected_exception_is_reduced_to_its_class(self):
        text = safe_error_text(KeyError(MARKER))
        self.assertNotIn(MARKER, text)
        self.assertIn("KeyError", text)

    def test_expected_exception_keeps_its_message(self):
        self.assertEqual(safe_error_text(RunUnavailable("No executor"), (RunUnavailable,)), "No executor")

    def test_subclass_of_expected_type_is_expected(self):
        self.assertEqual(safe_error_text(docker.errors.BuildError("pip failed", iter(())), (docker.errors.DockerException,)),
                         "pip failed")


def _boom_container():
    container = mock.Mock()
    container.wait.side_effect = RuntimeError(MARKER)
    container.logs.return_value = b""
    container.status = "exited"
    client = mock.Mock()
    client.containers.create.return_value = container
    return client


class ExecutorErrorTextTests(SimpleTestCase):
    FILE_CASES = [
        (PythonExecutor, "student.py", ".py"),
        (RExecutor, "student.R", ".R"),
        (NodeExecutor, "student.js", ".js"),
        (PHPExecutor, "student.php", ".php"),
        (RubyExecutor, "student.rb", ".rb"),
        (JavaExecutor, "Main.java", ".java"),
        (CPPExecutor, "main.cpp", ".cpp"),
    ]
    NOTEBOOK_CASES = [
        (PythonNotebookExecutor, "python"), (RNotebookExecutor, "R"), (NodeNotebookExecutor, "javascript"),
        (PHPNotebookExecutor, "php"), (RubyNotebookExecutor, "ruby"), (JavaNotebookExecutor, "java"),
    ]

    def _execute(self, executor):
        with mock.patch.object(Executor, "_get_docker_client", return_value=_boom_container()), \
                mock.patch.object(Executor, "_ensure_image", return_value=True):
            return executor.execute()

    def _assert_no_leak(self, result):
        self.assertFalse(result.success)
        self.assertNotIn(MARKER, json.dumps(result.to_dict(), default=str))
        self.assertTrue(result.err)

    def test_file_executors_do_not_echo_exception_text(self):
        for cls, name, ext in self.FILE_CASES:
            with self.subTest(executor=cls.__name__):
                self._assert_no_leak(self._execute(cls(_mock_file("x = 1\n", name, ext), test_code="pass")))

    def test_notebook_executors_do_not_echo_exception_text(self):
        for cls, language in self.NOTEBOOK_CASES:
            with self.subTest(executor=cls.__name__):
                self._assert_no_leak(self._execute(cls(_notebook_file(["x = 1"], language), test_code="pass")))

    def test_from_exception_logs_the_detail(self):
        with self.assertLogs(base_module.logger, level="ERROR") as logs:
            result = ExecutionResult.from_exception(RuntimeError(MARKER))
        self.assertNotIn(MARKER, result.err or "")
        self.assertIn(MARKER, "\n".join(logs.output))

    def _stream(self, executor):
        chunks = []
        with mock.patch.object(executor, "execute", side_effect=RuntimeError(MARKER)):
            try:
                for chunk in executor.execute_streaming(user=None):
                    chunks.append(chunk)
            except AttributeError:
                pass  # existing: the generator continues to result.save_cache with result None
        return "".join(chunks)

    def test_streaming_execution_failure_is_not_echoed(self):
        out = self._stream(PythonExecutor(_mock_file("x = 1\n", "student.py", ".py")))
        self.assertIn('"error"', out)
        self.assertNotIn(MARKER, out)

    def test_streaming_complete_message_failure_is_not_echoed(self):
        executor = PythonExecutor(_mock_file("x = 1\n", "student.py", ".py"))
        result = ExecutionResult(success=True)
        with mock.patch.object(executor, "execute", return_value=result), \
                mock.patch.object(ExecutionResult, "save_cache"), \
                mock.patch.object(ExecutionResult, "to_dict", side_effect=RuntimeError(MARKER)):
            out = "".join(executor.execute_streaming(user=None))
        self.assertIn("Failed to send complete message", out)
        self.assertNotIn(MARKER, out)


class _EventTestBase(TestCase):
    def setUp(self):
        self.assignment = AssignmentFactory()
        Environment.objects.filter(assignment=self.assignment).delete()
        self.environment = Environment.objects.create(assignment=self.assignment, language="python-3.12")
        self.submission = self.assignment.submissions.first()
        self.file = self.submission.files.first()
        self.user = User.objects.create_user(username="r@rutgers.edu", email="r@rutgers.edu", password="TestPass1!")


class TaskResultTextTests(_EventTestBase):
    def test_run_file_task_result_hides_exception_text(self):
        from autograder import tasks
        with mock.patch.object(tasks.Executor, "factory", side_effect=RuntimeError(MARKER)):
            response = tasks.run_file_task(self.file.id, self.user.id, force_execute=True)
        self.assertFalse(response["success"])
        self.assertNotIn(MARKER, json.dumps(response))

    def test_run_file_task_keeps_exception_text_in_superuser_stats(self):
        from autograder import tasks
        with mock.patch.object(tasks.Executor, "factory", side_effect=RuntimeError(MARKER)):
            tasks.run_file_task(self.file.id, self.user.id, force_execute=True)
        self.assertIn(MARKER, AutograderExecutionEvent.objects.get().error_detail)

    def test_run_test_task_result_hides_exception_text(self):
        from autograder import tasks
        with mock.patch("autograder.services.TestService.TestService.run_suite", side_effect=RuntimeError(MARKER)):
            response = tasks.run_test_task(self.submission.id)
        self.assertFalse(response["success"])
        self.assertNotIn(MARKER, json.dumps(response))

    def test_cleanup_images_task_result_hides_exception_text(self):
        from autograder import tasks
        with mock.patch("autograder.services.image_manager.ImageManager.cleanup_old_images",
                        side_effect=RuntimeError(MARKER)):
            response = tasks.cleanup_images_task(self.environment.id)
        self.assertFalse(response["success"])
        self.assertNotIn(MARKER, json.dumps(response))

    def test_streaming_task_error_event_hides_exception_text(self):
        from autograder import tasks
        redis_client = mock.Mock()
        with mock.patch.object(tasks, "_get_redis_client", return_value=redis_client), \
                mock.patch.object(tasks.Executor, "factory", side_effect=RuntimeError(MARKER)):
            tasks.run_file_streaming_task("chan", self.file.id, self.user.id)
        published = " ".join(call.args[1] for call in redis_client.publish.call_args_list)
        self.assertIn('"error"', published)
        self.assertNotIn(MARKER, published)


class StreamingViewTextTests(_EventTestBase):
    def test_view_level_unexpected_error_hides_exception_text(self):
        from autograder.views.executor_streaming import ExecuteFileStreaming
        request = mock.Mock(user=self.user)
        with mock.patch("autograder.tasks._get_redis_client", side_effect=RuntimeError(MARKER)):
            out = "".join(ExecuteFileStreaming()._execute_with_streaming(request, self.file, None, None, {}))
        self.assertIn('"error"', out)
        self.assertNotIn(MARKER, out)


class TestServiceErrorTextTests(TestCase):
    def setUp(self):
        from core.models import TestCase as CodepostTestCase
        from core.tests.factories import TestCategoryFactory
        with factory.django.mute_signals(post_save):
            self.course = CourseFactory(name="ag-leaks", period="s2026", organization__name="LeakOrg")
            self.assignment = self.course.assignments.first()
            self.category = TestCategoryFactory(assignment=self.assignment, testScript="")
            self.test_case = CodepostTestCase.objects.create(
                testCategory=self.category, functionName="test_first", description="first", type="script",
                pointsPass=2, testCode="@test(name='test_first')\ndef test_first():\n    pass\n")
            self.submission = self.assignment.submissions.first()

    def test_run_test_crash_hides_exception_text(self):
        from autograder.services.TestService import TestService
        with mock.patch.object(TestService, "_run_ephemeral_execution", side_effect=RuntimeError(MARKER)):
            result = TestService.run_test(self.test_case.id, self.submission.id)
        self.assertFalse(result["success"])
        self.assertNotIn(MARKER, json.dumps(result))

    def test_individual_test_crash_in_suite_hides_exception_text(self):
        from autograder.services.TestService import TestService
        with mock.patch.object(TestService, "run_test", side_effect=RuntimeError(MARKER)):
            results = TestService.run_suite(self.submission.id)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["success"])
        self.assertNotIn(MARKER, json.dumps(results))

    def test_suite_level_crash_hides_exception_text(self):
        from autograder.services.TestService import TestService
        with mock.patch.object(TestService, "_restrict_overrides", side_effect=RuntimeError(MARKER)):
            results = TestService.run_suite(self.submission.id)
        self.assertFalse(results[0]["success"])
        self.assertNotIn(MARKER, json.dumps(results))


class ShellRelayErrorTextTests(SimpleTestCase):
    def _relay(self):
        from autograder.worker_shell_relay import WorkerShellRelay
        with mock.patch("autograder.worker_shell_relay.redis_async.from_url"), \
                mock.patch("autograder.worker_shell_relay.redis.Redis.from_url"):
            return WorkerShellRelay("redis://unused", "worker-1")

    def test_start_failure_message_hides_exception_text(self):
        relay = self._relay()
        sent = []

        async def fake_apublish(client, channel, payload):
            sent.append(payload)

        with mock.patch("autograder.worker_shell_relay._apublish", fake_apublish), \
                mock.patch("autograder.worker_shell_relay.database_sync_to_async",
                           return_value=mock.AsyncMock(side_effect=RuntimeError(MARKER))):
            asyncio.run(relay._handle_start("s1", {"envId": 1, "userId": 1}))
        self.assertEqual(sent[0]["type"], "error")
        self.assertNotIn(MARKER, json.dumps(sent))

    def test_input_failure_message_hides_exception_text(self):
        relay = self._relay()
        sent = []

        async def fake_apublish(client, channel, payload):
            sent.append(payload)

        session = mock.Mock()
        session.socket._sock.sendall.side_effect = OSError(MARKER)
        relay.sessions["s1"] = session
        with mock.patch("autograder.worker_shell_relay._apublish", fake_apublish):
            asyncio.run(relay._handle_input("s1", {"data": "ls"}))
        self.assertEqual(sent[0]["type"], "error")
        self.assertNotIn(MARKER, json.dumps(sent))

    def test_read_loop_failure_message_hides_exception_text(self):
        relay = self._relay()
        sent = []
        sock = mock.Mock()
        sock._sock.recv.side_effect = OSError(MARKER)
        with mock.patch("autograder.worker_shell_relay._publish", lambda c, ch, payload: sent.append(payload)):
            relay._read_loop("s1", sock)
        self.assertEqual(sent[0]["type"], "error")
        self.assertNotIn(MARKER, json.dumps(sent))


class BuilderErrorTextTests(TestCase):
    def setUp(self):
        self.env = Environment.objects.create(assignment=AssignmentFactory(), language="python-3.12", auto_detect=False)

    def _build(self, api_build):
        from autograder.services.builder import Builder
        with mock.patch("autograder.services.builder.docker.from_env") as from_env:
            client = from_env.return_value
            client.api.build = api_build
            builder = Builder(self.env.id)
        with mock.patch("autograder.services.builder.ImageManager"):
            result = builder.build()
        self.env.refresh_from_db()
        return result

    def test_unexpected_build_exception_is_hidden_from_logs_and_result(self):
        result = self._build(mock.Mock(side_effect=RuntimeError(MARKER)))
        self.assertFalse(result["success"])
        self.assertNotIn(MARKER, json.dumps(result, default=str))
        self.assertNotIn(MARKER, self.env.build_logs)
        self.assertEqual(self.env.build_status, 3)

    def test_unexpected_build_exception_is_hidden_from_audit_event(self):
        from log.models import Event
        self._build(mock.Mock(side_effect=RuntimeError(MARKER)))
        self.assertFalse(Event.objects.filter(category="builder", meta__contains=MARKER).exists())

    def test_docker_build_failure_keeps_its_diagnostic(self):
        result = self._build(mock.Mock(return_value=iter([{"error": "pip install nopkg failed"}])))
        self.assertFalse(result["success"])
        self.assertIn("pip install nopkg failed", result["error"])
        self.assertIn("pip install nopkg failed", self.env.build_logs)

    def test_docker_api_error_keeps_its_diagnostic(self):
        result = self._build(mock.Mock(side_effect=docker.errors.APIError("daemon says no")))
        self.assertIn("daemon says no", self.env.build_logs)
        self.assertIn("daemon says no", result["error"])


class BuildEnvironmentTaskTextTests(TestCase):
    def _run(self, exc):
        from autograder.run import BuildEnvironment
        env = Environment.objects.create(assignment=AssignmentFactory(), language="python-3.12",
                                         auto_detect=False, build_status=1)
        with mock.patch("autograder.run.Builder", side_effect=exc):
            with self.assertRaises(Exception):
                BuildEnvironment(env.id)
        env.refresh_from_db()
        return env

    def test_unexpected_builder_init_error_is_hidden(self):
        env = self._run(RuntimeError(MARKER))
        self.assertNotIn(MARKER, env.build_logs)
        self.assertIn("cannot reach its Docker daemon", env.build_logs)

    def test_docker_daemon_error_keeps_its_diagnostic(self):
        env = self._run(docker.errors.DockerException("Cannot connect to the Docker daemon at unix:///x"))
        self.assertIn("Cannot connect to the Docker daemon", env.build_logs)


class EnvironmentBuildQueueTextTests(APITestCase):
    def test_queue_failure_build_logs_hide_exception_text(self):
        import kombu.exceptions
        with factory.django.mute_signals(post_save):
            course = CourseFactory(name="ag-queue", period="s2026", organization__name="QueueOrg")
        env = Environment.objects.create(assignment=course.assignments.first(), language="python-3.12", auto_detect=False)
        self.client.force_authenticate(user=course.courseAdmins.first())
        with mock.patch("autograder.run.BuildEnvironment.delay", side_effect=kombu.exceptions.OperationalError(MARKER)):
            self.client.patch(f"/autograder/environments/{env.id}/build/", {}, format="json")
        env.refresh_from_db()
        self.assertIn("Could not queue build", env.build_logs)
        self.assertNotIn(MARKER, env.build_logs)


class RunSubmissionTextTests(_EventTestBase):
    def _variant_result(self, factory_patch):
        from autograder.run import RunSubmissionVariant
        from core.models import AssignmentDataSet
        dataset = AssignmentDataSet.objects.create(assignment=self.assignment, name="d", is_student_variant=True)
        with factory_patch:
            RunSubmissionVariant(self.submission.id, dataset.id)
        return SubmissionVariantRun.objects.get(submission=self.submission, dataset=dataset).result

    def test_variant_run_hides_unexpected_exception_text(self):
        result = self._variant_result(mock.patch("autograder.run.Executor.factory", side_effect=RuntimeError(MARKER)))
        self.assertEqual(result["status"], "error")
        self.assertNotIn(MARKER, json.dumps(result))

    def test_variant_run_keeps_no_executor_diagnostic(self):
        result = self._variant_result(mock.patch("autograder.run.Executor.factory", return_value=None))
        self.assertEqual(result["error"], "No executable file found.")
