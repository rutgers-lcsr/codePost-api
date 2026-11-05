# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
A quiz with closeEvent='submission' and endAttemptsAtClose closes for each student at their
own submission time. An attempt already in progress when the student submits must be capped at
that moment, like quiz_close_time says (the stored attempt deadline follows the close).
"""
from datetime import timedelta

import factory
from django.db.models.signals import post_save
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import QuizAttempt, Submission
from core.tests.factories import CourseFactory
from core.tests.views.quiz_helpers import _add, _bank, _mc, _quiz


class AttemptDeadlineFollowsSubmissionTests(APITestCase):
    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.course = CourseFactory(name="cos333", period="s2026", organization__name="Princeton")
        self.assignment = self.course.assignments.first()
        self.assignment.state = 'published'
        self.assignment.save()
        self.student, self.other = list(self.course.students.all())[:2]

    def _start_attempt(self, student, **quiz_kwargs):
        kwargs = dict(assignmentTrigger='during', closeEvent='submission',
                      closeOffsetMinutes=0, endAttemptsAtClose=True)
        kwargs.update(quiz_kwargs)
        quiz = _quiz(self.course, assignment=self.assignment, **kwargs)
        _add(quiz, _mc(self.course, _bank(self.course)))
        self.client.force_authenticate(user=student)
        resp = self.client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return QuizAttempt.objects.get(pk=resp.data['id'])

    def _submit(self, student, when):
        with factory.django.mute_signals(post_save):
            sub = Submission.objects.create(assignment=self.assignment, dateUploaded=when)
            sub.students.add(student)

    def test_submitting_mid_attempt_caps_the_deadline_at_the_submission(self):
        attempt = self._start_attempt(self.student)
        self.assertIsNone(attempt.deadline)
        when = timezone.now()
        self._submit(self.student, when)
        attempt.refresh_from_db()
        self.assertEqual(attempt.deadline, when)

    def test_offset_is_added_to_the_submission_time(self):
        attempt = self._start_attempt(self.student, closeOffsetMinutes=30)
        when = timezone.now()
        self._submit(self.student, when)
        attempt.refresh_from_db()
        self.assertEqual(attempt.deadline, when + timedelta(minutes=30))

    def test_time_limit_still_wins_when_it_is_shorter(self):
        attempt = self._start_attempt(self.student, timeLimitMinutes=5)
        limit = attempt.deadline
        self._submit(self.student, timezone.now() + timedelta(hours=1))
        attempt.refresh_from_db()
        self.assertEqual(attempt.deadline, limit)

    def test_other_students_attempt_is_untouched(self):
        attempt = self._start_attempt(self.other)
        self._submit(self.student, timezone.now())
        attempt.refresh_from_db()
        self.assertIsNone(attempt.deadline)

    def test_quiz_that_does_not_end_attempts_at_close_is_untouched(self):
        attempt = self._start_attempt(self.student, endAttemptsAtClose=False)
        self._submit(self.student, timezone.now())
        attempt.refresh_from_db()
        self.assertIsNone(attempt.deadline)

    def test_resubmitting_keeps_the_earliest_close(self):
        attempt = self._start_attempt(self.student)
        first = timezone.now()
        self._submit(self.student, first)
        self._submit(self.student, first + timedelta(hours=1))
        attempt.refresh_from_db()
        self.assertEqual(attempt.deadline, first)

    def test_quiz_with_a_different_close_event_is_untouched(self):
        attempt = self._start_attempt(self.student, closeEvent='fixed_date',
                                      availableUntil=timezone.now() + timedelta(days=1))
        before = attempt.deadline
        self._submit(self.student, timezone.now())
        attempt.refresh_from_db()
        self.assertEqual(attempt.deadline, before)
