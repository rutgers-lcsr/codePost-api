# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for the run_scheduled_feedback_release beat sweep (mirrors the
scheduled-publish suite)."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import CourseAuditEvent
from core.tasks import run_scheduled_feedback_release
from core.tests.factories import AssignmentFactory


def _arm(assignment, status='hidden', minutes_ago=5):
  assignment.feedbackStatus = status
  assignment.releaseFeedbackAt = timezone.now() - timedelta(minutes=minutes_ago)
  assignment.save()
  return assignment


class TestScheduledFeedbackRelease(TestCase):

  def setUp(self):
    self.assignment = AssignmentFactory(state='published')

  def test_runs_when_due_from_hidden(self):
    _arm(self.assignment)
    self.assertEqual(run_scheduled_feedback_release(), 1)
    self.assignment.refresh_from_db()
    self.assertEqual(self.assignment.feedbackStatus, 'released')
    self.assertIsNotNone(self.assignment.scheduledFeedbackReleaseRanAt)
    self.assertIsNotNone(self.assignment.feedbackReleasedAt)  # save() stamped the anchor
    event = CourseAuditEvent.objects.filter(
        event_type='assignment_feedback_changed', assignment=self.assignment).last()
    self.assertIsNotNone(event)
    self.assertTrue(event.meta.get('scheduled'))

  def test_runs_from_per_student(self):
    _arm(self.assignment, status='per_student')
    self.assertEqual(run_scheduled_feedback_release(), 1)
    self.assignment.refresh_from_db()
    self.assertEqual(self.assignment.feedbackStatus, 'released')

  def test_one_shot(self):
    _arm(self.assignment)
    run_scheduled_feedback_release()
    self.assertEqual(run_scheduled_feedback_release(), 0)

  def test_skips_before_date(self):
    _arm(self.assignment, minutes_ago=-60)
    self.assertEqual(run_scheduled_feedback_release(), 0)
    self.assignment.refresh_from_db()
    self.assertEqual(self.assignment.feedbackStatus, 'hidden')

  def test_rearm_when_date_moved_forward(self):
    _arm(self.assignment)
    run_scheduled_feedback_release()
    self.assignment.refresh_from_db()
    stamp = self.assignment.scheduledFeedbackReleaseRanAt

    self.assignment.feedbackStatus = 'hidden'
    self.assignment.releaseFeedbackAt = stamp
    self.assignment.save()
    self.assertEqual(run_scheduled_feedback_release(), 0)

    self.assignment.releaseFeedbackAt = timezone.now()
    self.assignment.save()
    self.assertEqual(run_scheduled_feedback_release(), 1)

  def test_skips_live_released_and_archived_course(self):
    past = timezone.now() - timedelta(minutes=5)
    for status in ('live', 'released'):
      self.assignment.feedbackStatus = status
      self.assignment.releaseFeedbackAt = past
      self.assignment.save()
      self.assertEqual(run_scheduled_feedback_release(), 0, status)

    self.assignment.feedbackStatus = 'hidden'
    self.assignment.save()
    self.assignment.course.archived = True
    self.assignment.course.save()
    self.assertEqual(run_scheduled_feedback_release(), 0)

  def test_release_at_pushed_forward_after_snapshot_is_not_released(self):
    from unittest import mock
    from core.models import Assignment
    from core.services import audit
    _arm(self.assignment)
    _arm(AssignmentFactory(state='published', name='second', course=self.assignment.course))
    real_record = audit.record_audit_event

    def push_forward_others(*args, **kwargs):
      Assignment.objects.exclude(pk=kwargs['assignment'].pk).update(
          releaseFeedbackAt=timezone.now() + timedelta(days=1))
      return real_record(*args, **kwargs)

    with mock.patch('core.services.audit.record_audit_event', push_forward_others):
      count = run_scheduled_feedback_release()
    self.assertEqual(count, 1)
    self.assertEqual(Assignment.objects.filter(feedbackStatus='released').count(), 1)
