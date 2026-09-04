# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests that the autograder execution paths record AutograderExecutionEvent rows
(cache hits, misses, and failures) for the superadmin stats dashboard.
"""
from unittest import mock

from django.test import TestCase

from autograder.services.executors.base import ExecutionResult
from core.models import AutograderExecutionEvent, Environment, User
from core.tests.factories import AssignmentFactory


class ExecutionEventBaseTestCase(TestCase):

    def setUp(self):
        self.assignment = AssignmentFactory()
        Environment.objects.filter(assignment=self.assignment).delete()
        self.environment = Environment.objects.create(
            assignment=self.assignment, language='python-3.12')
        self.submission = self.assignment.submissions.first()
        self.file = self.submission.files.first()
        self.user = User.objects.create_user(
            username='runner@rutgers.edu', email='runner@rutgers.edu', password='TestPass1!')

    def _fake_executor(self, result):
        executor = mock.Mock()
        executor.execute.return_value = result
        return executor


class RunFileTaskEventsTestCase(ExecutionEventBaseTestCase):

    def test_cache_hit_recorded(self):
        from autograder.tasks import run_file_task
        ExecutionResult(success=True, stdout='ok').save_cache(self.file, self.user)
        AutograderExecutionEvent.objects.all().delete()  # drop the seed event

        response = run_file_task(self.file.id, self.user.id)
        self.assertTrue(response.get('cached'))

        event = AutograderExecutionEvent.objects.get()
        self.assertEqual(event.trigger, 'file_run')
        self.assertTrue(event.cached)
        self.assertTrue(event.success)
        self.assertEqual(event.language, 'python-3.12')
        self.assertEqual(event.course_id, self.assignment.course_id)
        self.assertEqual(event.assignment_id, self.assignment.id)

    def test_cache_miss_failure_recorded_and_classified(self):
        from autograder import tasks
        failing = ExecutionResult(
            success=False, stderr="ModuleNotFoundError: No module named 'numpy'",
            err="ModuleNotFoundError: No module named 'numpy'")
        with mock.patch.object(tasks.Executor, 'factory',
                               return_value=self._fake_executor(failing)):
            tasks.run_file_task(self.file.id, self.user.id, force_execute=True)

        event = AutograderExecutionEvent.objects.get()
        self.assertEqual(event.trigger, 'file_run')
        self.assertFalse(event.cached)
        self.assertFalse(event.success)
        self.assertEqual(event.error_category, 'missing_dependency')
        self.assertIn('numpy', event.error_message)

    def test_task_exception_recorded_as_failure(self):
        from autograder import tasks
        with mock.patch.object(tasks.Executor, 'factory',
                               side_effect=RuntimeError('docker daemon unreachable')):
            response = tasks.run_file_task(self.file.id, self.user.id, force_execute=True)

        self.assertFalse(response['success'])
        event = AutograderExecutionEvent.objects.get()
        self.assertFalse(event.success)
        self.assertEqual(event.error_category, 'infra')
        self.assertEqual(event.course_id, self.assignment.course_id)


class GetOrRunExecutionEventsTestCase(ExecutionEventBaseTestCase):

    def test_cache_hit_recorded(self):
        from autograder.services.TestService import TestService
        ExecutionResult(success=True, stdout='ok').save_cache(self.file, self.user)
        AutograderExecutionEvent.objects.all().delete()

        result = TestService._get_or_run_execution(self.file)
        self.assertTrue(result['cached'])

        event = AutograderExecutionEvent.objects.get()
        self.assertEqual(event.trigger, 'test_run')
        self.assertTrue(event.cached)
        self.assertTrue(event.success)

    def test_cache_miss_recorded(self):
        from autograder.services import TestService as ts_module
        result = ExecutionResult(success=True, stdout='ok')
        with mock.patch.object(ts_module.Executor, 'factory',
                               return_value=self._fake_executor(result)):
            outcome = ts_module.TestService._get_or_run_execution(self.file)

        self.assertFalse(outcome['cached'])
        event = AutograderExecutionEvent.objects.get()
        self.assertEqual(event.trigger, 'test_run')
        self.assertFalse(event.cached)
        self.assertTrue(event.success)


class RunSubmissionEventsTestCase(ExecutionEventBaseTestCase):

    def test_one_event_per_file_with_language_snapshot(self):
        from autograder import run as run_module

        result = ExecutionResult(success=True, stdout='ok')
        with mock.patch.object(run_module.Executor, 'factory',
                               return_value=self._fake_executor(result)), \
             mock.patch.object(run_module.TestService, 'run_suite', return_value=[]), \
             mock.patch('autograder.services.autodetector.Autodetector.detect_and_update'):
            run_module.RunSubmission(self.submission.id)

        events = AutograderExecutionEvent.objects.filter(trigger='submission_run')
        self.assertEqual(events.count(), self.submission.files.count())
        for event in events:
            self.assertFalse(event.cached)
            self.assertTrue(event.success)
            self.assertEqual(event.language, 'python-3.12')
            self.assertEqual(event.assignment_id, self.assignment.id)
