# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for the reap_stale_autograder_state beat sweep."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import Assignment, Environment, QuizAttempt, QuizResponse
from core.tasks import reap_stale_autograder_state
from core.tests.factories import AssignmentFactory
from core.tests.views.quiz_helpers import _bank, _code, _quiz


def _backdate(model, pk, minutes):
  model.objects.filter(pk=pk).update(modified=timezone.now() - timedelta(minutes=minutes))


class TestReapStaleAutograderState(TestCase):

  def setUp(self):
    self.assignment = AssignmentFactory()
    self.course = self.assignment.course

  def test_stale_building_environment_is_marked_failed(self):
    env = Environment.objects.create(assignment=self.assignment, language='python-3.12',
                                     build_status=1, build_logs='Building image...\n')
    _backdate(Environment, env.pk, 31)

    self.assertEqual(reap_stale_autograder_state()['builds'], 1)
    env.refresh_from_db()
    self.assertEqual(env.build_status, 3)
    self.assertIn('no build progress for 30 min', env.build_logs)

  def test_recent_or_finished_builds_are_untouched(self):
    fresh = Environment.objects.create(assignment=self.assignment, language='python-3.12', build_status=1)
    other = Assignment.objects.create(name='HW2', course=self.course, points=10)
    done = Environment.objects.create(assignment=other, language='python-3.12', build_status=2)
    _backdate(Environment, done.pk, 60)

    self.assertEqual(reap_stale_autograder_state()['builds'], 0)
    fresh.refresh_from_db()
    done.refresh_from_db()
    self.assertEqual(fresh.build_status, 1)
    self.assertEqual(done.build_status, 2)

  def test_stale_running_code_execution_is_errored(self):
    bank = _bank(self.course)
    quiz = _quiz(self.course)
    student = User.objects.create_user(username='stu@reap.org', email='stu@reap.org', password='pw')
    attempt = QuizAttempt.objects.create(quiz=quiz, student=student)
    stale = attempt.responses.create(question=_code(self.course, bank), questionSnapshot={},
                                     codeExecution={'status': 'running', 'requestedBy': 'grader@reap.org'})
    fresh = attempt.responses.create(question=_code(self.course, bank), questionSnapshot={},
                                     codeExecution={'status': 'running'})
    finished = attempt.responses.create(question=_code(self.course, bank), questionSnapshot={},
                                        codeExecution={'status': 'success', 'stdout': '5.5'})
    _backdate(QuizResponse, stale.pk, 11)
    _backdate(QuizResponse, finished.pk, 11)

    self.assertEqual(reap_stale_autograder_state()['code_runs'], 1)
    stale.refresh_from_db()
    fresh.refresh_from_db()
    finished.refresh_from_db()
    self.assertEqual(stale.codeExecution['status'], 'error')
    self.assertEqual(stale.codeExecution['requestedBy'], 'grader@reap.org')  # other keys preserved
    self.assertIn('finishedAt', stale.codeExecution)
    self.assertEqual(fresh.codeExecution['status'], 'running')
    self.assertEqual(finished.codeExecution['status'], 'success')
