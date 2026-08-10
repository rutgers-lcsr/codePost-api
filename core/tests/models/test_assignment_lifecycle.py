# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Unit tests for the Assignment lifecycle: submission_deadline / effective_state,
the state <-> legacy-boolean sync in save(), and the publishedAt stamp."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import Assignment
from core.tests.factories import AssignmentFactory, CourseFactory


class TestSubmissionDeadline(TestCase):

  def setUp(self):
    self.assignment = AssignmentFactory(state='published')

  def test_no_due_date_means_no_deadline(self):
    self.assignment.uploadDueDate = None
    self.assertIsNone(self.assignment.submission_deadline())

  def test_deadline_is_due_date_without_late_uploads(self):
    due = timezone.now()
    self.assignment.uploadDueDate = due
    self.assignment.allowLateUploads = False
    self.assertEqual(self.assignment.submission_deadline(), due)

  def test_late_uploads_extend_by_max_late_days(self):
    due = timezone.now()
    self.assignment.uploadDueDate = due
    self.assignment.allowLateUploads = True
    self.assignment.maxLateDays = 3
    self.assertEqual(self.assignment.submission_deadline(), due + timedelta(days=3))


class TestEffectiveState(TestCase):

  def setUp(self):
    self.assignment = AssignmentFactory(state='published')

  def test_non_published_states_pass_through(self):
    for state in ('draft', 'visible', 'preview', 'closed', 'archived'):
      self.assignment.state = state
      self.assignment.uploadDueDate = timezone.now() - timedelta(days=30)
      self.assertEqual(self.assignment.effective_state(), state)

  def test_published_without_deadline_never_closes(self):
    self.assignment.uploadDueDate = None
    self.assertEqual(self.assignment.effective_state(), 'published')

  def test_published_past_deadline_reads_closed(self):
    self.assignment.uploadDueDate = timezone.now() - timedelta(days=1)
    self.assignment.allowLateUploads = False
    self.assertEqual(self.assignment.effective_state(), 'closed')

  def test_late_window_keeps_published(self):
    self.assignment.uploadDueDate = timezone.now() - timedelta(days=1)
    self.assignment.allowLateUploads = True
    self.assignment.maxLateDays = 2
    self.assertEqual(self.assignment.effective_state(), 'published')

  def test_exhausted_late_window_reads_closed(self):
    self.assignment.uploadDueDate = timezone.now() - timedelta(days=3)
    self.assignment.allowLateUploads = True
    self.assignment.maxLateDays = 2
    self.assertEqual(self.assignment.effective_state(), 'closed')

  def test_stored_closed_wins_regardless_of_clock(self):
    self.assignment.state = 'closed'
    self.assignment.uploadDueDate = timezone.now() + timedelta(days=30)
    self.assertEqual(self.assignment.effective_state(), 'closed')


class TestLifecycleBooleanSync(TestCase):
  """state is the source of truth; the legacy booleans stay derived — and legacy
  writers that flip the booleans directly get state re-derived (migration 0140's
  mapping) until Phase 4 removes them."""

  def test_state_change_derives_booleans(self):
    a = AssignmentFactory(state='preview')
    self.assertTrue(a.isVisible)
    self.assertFalse(a.isReleased)

    a.state = 'published'
    a.save()
    a.refresh_from_db()
    self.assertTrue(a.isVisible)
    self.assertTrue(a.isReleased)

    a.state = 'draft'
    a.save()
    a.refresh_from_db()
    self.assertFalse(a.isVisible)
    self.assertFalse(a.isReleased)

    a.state = 'closed'
    a.save()
    a.refresh_from_db()
    self.assertTrue(a.isVisible)
    self.assertTrue(a.isReleased)

    a.state = 'archived'
    a.save()
    a.refresh_from_db()
    self.assertFalse(a.isVisible)
    self.assertFalse(a.isReleased)

  def test_legacy_boolean_write_rederives_state(self):
    a = AssignmentFactory(state='preview')

    a.isReleased = True
    a.save()
    a.refresh_from_db()
    self.assertEqual(a.state, 'published')

    a.isVisible = False
    a.save()
    a.refresh_from_db()
    self.assertEqual(a.state, 'draft')
    self.assertFalse(a.isReleased)  # normalized: hidden wins

  def test_legacy_create_with_released_flag(self):
    a = Assignment.objects.create(
        name='legacy', points=10, course=CourseFactory(), isReleased=True)
    self.assertEqual(a.state, 'published')
    self.assertTrue(a.isVisible)

  def test_state_change_wins_over_stale_booleans(self):
    a = AssignmentFactory(state='published')
    a.state = 'draft'
    # booleans left stale (True) — the state change must win and re-derive them
    a.save()
    a.refresh_from_db()
    self.assertEqual(a.state, 'draft')
    self.assertFalse(a.isVisible)
    self.assertFalse(a.isReleased)


class TestPublishedAtStamp(TestCase):

  def test_stamped_on_publish_and_kept_on_close(self):
    a = AssignmentFactory(state='preview')
    self.assertIsNone(a.publishedAt)

    a.state = 'published'
    a.save()
    a.refresh_from_db()
    self.assertIsNotNone(a.publishedAt)
    stamped = a.publishedAt

    a.state = 'closed'
    a.save()
    a.refresh_from_db()
    self.assertEqual(a.publishedAt, stamped)  # close keeps the stamp

    a.state = 'draft'
    a.save()
    a.refresh_from_db()
    self.assertIsNone(a.publishedAt)  # back to pre-published clears it
