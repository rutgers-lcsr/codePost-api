# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for the run_scheduled_assignment_publish beat sweep (mirrors the
TestScheduledGeneration suite for quizzes)."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import CourseAuditEvent
from core.tasks import run_scheduled_assignment_publish
from core.tests.factories import AssignmentFactory


def _arm(assignment, state='visible', minutes_ago=5):
  assignment.state = state
  assignment.publishAt = timezone.now() - timedelta(minutes=minutes_ago)
  assignment.save()
  return assignment


class TestScheduledAssignmentPublish(TestCase):

  def setUp(self):
    self.assignment = AssignmentFactory(state='visible')

  def test_runs_when_due_from_visible(self):
    _arm(self.assignment, state='visible')
    count = run_scheduled_assignment_publish()
    self.assertEqual(count, 1)
    self.assignment.refresh_from_db()
    self.assertEqual(self.assignment.state, 'published')
    self.assertIsNotNone(self.assignment.scheduledPublishRanAt)
    self.assertIsNotNone(self.assignment.publishedAt)
    event = CourseAuditEvent.objects.filter(
        event_type='assignment_state_changed', assignment=self.assignment).last()
    self.assertIsNotNone(event)
    self.assertTrue(event.meta.get('scheduled'))

  def test_runs_when_due_from_preview(self):
    _arm(self.assignment, state='preview')
    self.assertEqual(run_scheduled_assignment_publish(), 1)
    self.assignment.refresh_from_db()
    self.assertEqual(self.assignment.state, 'published')

  def test_one_shot(self):
    _arm(self.assignment)
    run_scheduled_assignment_publish()
    self.assertEqual(run_scheduled_assignment_publish(), 0)

  def test_skips_before_date(self):
    _arm(self.assignment, minutes_ago=-60)  # an hour in the future
    self.assertEqual(run_scheduled_assignment_publish(), 0)
    self.assignment.refresh_from_db()
    self.assertEqual(self.assignment.state, 'visible')
    self.assertIsNone(self.assignment.scheduledPublishRanAt)

  def test_rearm_when_date_moved_forward(self):
    _arm(self.assignment)
    run_scheduled_assignment_publish()
    self.assignment.refresh_from_db()
    stamp = self.assignment.scheduledPublishRanAt

    # Unpublish and set a date at/before the stamp: stays quiet.
    self.assignment.state = 'visible'
    self.assignment.publishAt = stamp
    self.assignment.save()
    self.assertEqual(run_scheduled_assignment_publish(), 0)

    # A date after the stamp re-arms.
    self.assignment.publishAt = timezone.now()
    self.assignment.save()
    self.assertEqual(run_scheduled_assignment_publish(), 1)
    self.assignment.refresh_from_db()
    self.assertEqual(self.assignment.state, 'published')

  def test_skips_draft_archived_and_archived_course(self):
    past = timezone.now() - timedelta(minutes=5)

    self.assignment.state = 'draft'
    self.assignment.publishAt = past
    self.assignment.save()
    self.assertEqual(run_scheduled_assignment_publish(), 0)

    self.assignment.state = 'archived'
    self.assignment.save()
    self.assertEqual(run_scheduled_assignment_publish(), 0)

    self.assignment.state = 'visible'
    self.assignment.save()
    self.assignment.course.archived = True
    self.assignment.course.save()
    self.assertEqual(run_scheduled_assignment_publish(), 0)

  def test_failure_is_isolated(self):
    _arm(self.assignment)
    other = _arm(AssignmentFactory(state='visible', name='second', course=self.assignment.course))

    from unittest import mock
    real_save = type(self.assignment).save

    def failing_save(instance, *args, **kwargs):
      if instance.pk == self.assignment.pk:
        raise RuntimeError('boom')
      return real_save(instance, *args, **kwargs)

    with mock.patch.object(type(self.assignment), 'save', failing_save):
      count = run_scheduled_assignment_publish()
    self.assertEqual(count, 1)  # the healthy row still published
    other.refresh_from_db()
    self.assertEqual(other.state, 'published')

  def test_row_pulled_back_after_snapshot_is_not_published(self):
    """An instructor who moves a due row to draft after the sweep took its id snapshot
    must not see it published when the sweep reaches it."""
    from unittest import mock
    from core.models import Assignment
    from core.services import audit
    _arm(self.assignment)
    second = _arm(AssignmentFactory(state='visible', name='second', course=self.assignment.course))
    real_record = audit.record_audit_event

    def pull_back_others(*args, **kwargs):
      Assignment.objects.exclude(pk=kwargs['assignment'].pk).update(state='draft')
      return real_record(*args, **kwargs)

    with mock.patch('core.services.audit.record_audit_event', pull_back_others):
      count = run_scheduled_assignment_publish()
    self.assertEqual(count, 1)
    self.assertEqual(Assignment.objects.filter(state='published').count(), 1)
    second.refresh_from_db()
    self.assertEqual(second.state, 'draft')

  def test_publish_at_pushed_forward_after_snapshot_is_not_published(self):
    from unittest import mock
    from core.models import Assignment
    from core.services import audit
    _arm(self.assignment)
    _arm(AssignmentFactory(state='visible', name='second', course=self.assignment.course))
    real_record = audit.record_audit_event

    def push_forward_others(*args, **kwargs):
      Assignment.objects.exclude(pk=kwargs['assignment'].pk).update(
          publishAt=timezone.now() + timedelta(days=1))
      return real_record(*args, **kwargs)

    with mock.patch('core.services.audit.record_audit_event', push_forward_others):
      count = run_scheduled_assignment_publish()
    self.assertEqual(count, 1)
    self.assertEqual(Assignment.objects.filter(state='published').count(), 1)
