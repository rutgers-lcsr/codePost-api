# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Unit tests for the feedback axis: the helper predicates across all four
feedbackStatus states × hideGrades × isFinalized, and the feedbackReleasedAt stamp."""
from django.test import TestCase

from core.models import Submission
from core.permissions.helpers import (
    assignmentFeedbackOpen,
    feedbackOpenForSubmission,
    gradesVisibleForSubmission,
)
# Aliased: pytest would otherwise collect the test-prefixed helper name as a test.
from core.permissions.helpers import testResultsVisibleForSubmission as resultsVisibleForSubmission
from core.tests.factories import AssignmentFactory, StudentFactory


class TestFeedbackPredicates(TestCase):

  def setUp(self):
    self.assignment = AssignmentFactory(state='published')
    self.submission = self.assignment.submissions.first()
    self.student = StudentFactory(course='fbx', organization=self.assignment.course.organization, count=900)
    self.assignment.course.students.add(self.student)
    self.submission.students.add(self.student)

  def _set(self, status, finalized=False, hide_grades=False):
    self.assignment.feedbackStatus = status
    self.assignment.hideGrades = hide_grades
    self.assignment.save()
    Submission.objects.filter(pk=self.submission.pk).update(isFinalized=finalized)
    self.submission.refresh_from_db()
    return self.submission

  def test_feedback_open_matrix(self):
    # (status, finalized) -> open
    cases = {
        ('hidden', False): False,
        ('hidden', True): False,
        ('live', False): True,
        ('live', True): True,
        ('per_student', False): False,
        ('per_student', True): True,
        ('released', False): True,   # cap-level open; content gates add isFinalized
        ('released', True): True,
    }
    for (status, finalized), expected in cases.items():
      sub = self._set(status, finalized)
      self.assertEqual(feedbackOpenForSubmission(sub), expected, (status, finalized))

  def test_grades_visibility_respects_hide_grades_in_every_state(self):
    for status in ('live', 'per_student', 'released'):
      sub = self._set(status, finalized=True, hide_grades=False)
      self.assertTrue(gradesVisibleForSubmission(sub), status)
      sub = self._set(status, finalized=True, hide_grades=True)
      self.assertFalse(gradesVisibleForSubmission(sub), f"{status}+hideGrades")
    sub = self._set('hidden', finalized=True, hide_grades=False)
    self.assertFalse(gradesVisibleForSubmission(sub))

  def test_test_results_matrix(self):
    cases = {
        ('hidden', True): False,
        ('live', False): True,          # live shows results immediately
        ('per_student', False): False,
        ('per_student', True): True,
        ('released', False): False,     # released still requires finalization
        ('released', True): True,
    }
    for (status, finalized), expected in cases.items():
      sub = self._set(status, finalized)
      self.assertEqual(resultsVisibleForSubmission(sub), expected, (status, finalized))

  def test_assignment_level_gate_per_student(self):
    self._set('per_student', finalized=False)
    self.assertFalse(assignmentFeedbackOpen(self.assignment, self.student))
    self._set('per_student', finalized=True)
    self.assertTrue(assignmentFeedbackOpen(self.assignment, self.student))
    # A classmate without a finalized submission stays closed
    other = StudentFactory(course='fbx', organization=self.assignment.course.organization, count=901)
    self.assignment.course.students.add(other)
    self.assertFalse(assignmentFeedbackOpen(self.assignment, other))

  def test_assignment_level_gate_global_states(self):
    for status, expected in (('hidden', False), ('live', True), ('released', True)):
      self.assignment.feedbackStatus = status
      self.assignment.save()
      self.assertEqual(assignmentFeedbackOpen(self.assignment, self.student), expected, status)


class TestFeedbackReleasedAtStamp(TestCase):

  def test_stamped_on_released_only(self):
    a = AssignmentFactory(state='published')
    self.assertIsNone(a.feedbackReleasedAt)

    a.feedbackStatus = 'released'
    a.save()
    a.refresh_from_db()
    self.assertIsNotNone(a.feedbackReleasedAt)

    # Leaving released clears the anchor (quiz close events re-sync via signal)
    a.feedbackStatus = 'per_student'
    a.save()
    a.refresh_from_db()
    self.assertIsNone(a.feedbackReleasedAt)

    # live does not stamp — there is no global release moment
    a.feedbackStatus = 'live'
    a.save()
    a.refresh_from_db()
    self.assertIsNone(a.feedbackReleasedAt)
