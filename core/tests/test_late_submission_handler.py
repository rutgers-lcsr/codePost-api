# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from core.handlers.late_submission_handler import LateSubmissionHandler
from core.models import Comment, CommentTag, Submission
from core.tests.utils import setUpBase


class TestLateSubmissionHandlerReHandle(APITestCase):

  def setUp(self):
    setUpBase(self)
    CommentTag.objects.get_or_create(label='late')
    self.course.lateDayCreditsAllowable = 5
    self.course.save()
    self.assignment = self.DB['Assignment']
    self.assignment.lateDeductions = [2, 4, 8]
    self.assignment.uploadDueDate = timezone.now() - timedelta(days=3)
    self.assignment.save()
    self.submission = Submission.objects.get(pk=self.DB['Submission'].pk)
    self.submission.students.add(self.course.students.first())
    self.submission.dateUploaded = timezone.now()
    self.submission.save()

  def _late_comments(self):
    return [c for c in Comment.objects.filter(file__submission=self.submission)
            if 'late' in c.tags.values_list('label', flat=True)]

  def _handle(self):
    submission = Submission.objects.get(pk=self.submission.pk)
    LateSubmissionHandler(submission).handle()
    submission.refresh_from_db()
    return submission

  def test_no_longer_late_clears_credits_and_late_comment(self):
    late = self._handle()
    self.assertEqual(late.lateDayCreditsUsed, 2)
    self.assertEqual(len(self._late_comments()), 1)

    # The instructor extends the due date; the submission is re-handled.
    self.assignment.uploadDueDate = timezone.now() + timedelta(days=1)
    self.assignment.save()
    ontime = self._handle()

    self.assertEqual(ontime.lateDayCreditsUsed, 0)
    self.assertEqual(self._late_comments(), [])

  def test_rehandling_is_idempotent(self):
    self._handle()
    self.assignment.uploadDueDate = timezone.now() + timedelta(days=1)
    self.assignment.save()
    self._handle()
    again = self._handle()

    self.assertEqual(again.lateDayCreditsUsed, 0)
    self.assertEqual(self._late_comments(), [])

  def test_still_late_keeps_a_single_late_comment(self):
    self._handle()
    again = self._handle()

    self.assertEqual(again.lateDayCreditsUsed, 2)
    self.assertEqual(len(self._late_comments()), 1)
