# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests that every call site of record_audit_event() successfully records
a CourseAuditEvent with correct event_type, user, assignment, submission,
and meta fields.

Covered event types and their originating paths:
- submission_attempt   (AssignmentViewSet.studentUpload, SubmissionViewSet.perform_create)
- submission_failed    (SubmissionViewSet.create exception handler)
- file_view            (SubmissionViewSet.checkPermission — student, no feedback)
- feedback_view        (SubmissionViewSet.checkPermission — student, with feedback)
- regrade_request      (SubmissionViewSet.submitRegrade)
- regrade_deleted      (SubmissionViewSet.deleteRegrade)
- autograder_triggered (RunSubmission celery task)
- autograder_completed (RunSubmission celery task — no failures)
- autograder_failed    (RunSubmission celery task — with failures)
- late_day_used        (SubmissionSerializer.validate, AssignmentViewSet.studentUpload)
- comment_feedback     (CommentViewSet.feedback)
"""
from unittest.mock import MagicMock, patch

from django.db.models.signals import post_save
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APITestCase

import factory.django

from core.models import (
    CourseAuditEvent,
    Assignment,
    Submission,
    SubmissionFile,
    Environment,
    Quiz,
)
from core.services.audit import record_audit_event
from core.tests.factories import (
    CourseFactory,
    OrganizationFactory,
    UserFactory,
)


# ===========================================================================
# Unit tests: record_audit_event for every event type
# ===========================================================================

class TestRecordAuditEventAllTypes(TestCase):
    """Directly call record_audit_event for every EVENT_TYPE_CHOICES value
    and verify the created CourseAuditEvent."""

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.org = OrganizationFactory(name='AuditPathOrg', shortname='apo')
            self.course = CourseFactory(name='audit_path', period='s2026', organization=self.org)
        self.assignment = self.course.assignments.first()
        self.submission = self.assignment.submissions.first()
        self.user = self.course.students.first()
        self.quiz = Quiz.objects.create(course=self.course, title='Audit Quiz')

    def _assert_event(self, event, event_type, user=None, assignment=None, submission=None, meta=None):
        self.assertIsNotNone(event, f"record_audit_event returned None for {event_type}")
        self.assertEqual(event.event_type, event_type)
        self.assertEqual(event.course_id, self.course.id)
        if user:
            self.assertEqual(event.user_id, user.id)
        if assignment:
            self.assertEqual(event.assignment_id, assignment.id)
        if submission:
            self.assertEqual(event.submission_id, submission.id)
        if meta is not None:
            self.assertEqual(event.meta, meta)

    def test_submission_attempt(self):
        event = record_audit_event(
            course=self.course, event_type='submission_attempt',
            user=self.user, assignment=self.assignment, submission=self.submission,
        )
        self._assert_event(event, 'submission_attempt', self.user, self.assignment, self.submission)

    def test_submission_failed(self):
        meta = {'error': 'File too large'}
        event = record_audit_event(
            course=self.course, event_type='submission_failed',
            user=self.user, assignment=self.assignment, meta=meta,
        )
        self._assert_event(event, 'submission_failed', self.user, self.assignment, meta=meta)

    def test_file_view(self):
        event = record_audit_event(
            course=self.course, event_type='file_view',
            user=self.user, assignment=self.assignment, submission=self.submission,
        )
        self._assert_event(event, 'file_view', self.user, self.assignment, self.submission)

    def test_feedback_view(self):
        event = record_audit_event(
            course=self.course, event_type='feedback_view',
            user=self.user, assignment=self.assignment, submission=self.submission,
        )
        self._assert_event(event, 'feedback_view', self.user, self.assignment, self.submission)

    def test_regrade_request(self):
        meta = {'questionText': 'Please review Q3', 'isRegrade': True}
        event = record_audit_event(
            course=self.course, event_type='regrade_request',
            user=self.user, assignment=self.assignment, submission=self.submission, meta=meta,
        )
        self._assert_event(event, 'regrade_request', self.user, self.assignment, self.submission, meta)

    def test_regrade_deleted(self):
        event = record_audit_event(
            course=self.course, event_type='regrade_deleted',
            user=self.user, assignment=self.assignment, submission=self.submission,
        )
        self._assert_event(event, 'regrade_deleted', self.user, self.assignment, self.submission)

    def test_autograder_triggered(self):
        event = record_audit_event(
            course=self.course, event_type='autograder_triggered',
            user=self.user, assignment=self.assignment, submission=self.submission,
        )
        self._assert_event(event, 'autograder_triggered', self.user, self.assignment, self.submission)

    def test_autograder_completed(self):
        meta = {'successful': 3, 'test_results_count': 5}
        event = record_audit_event(
            course=self.course, event_type='autograder_completed',
            user=self.user, assignment=self.assignment, submission=self.submission, meta=meta,
        )
        self._assert_event(event, 'autograder_completed', self.user, self.assignment, self.submission, meta)

    def test_autograder_failed(self):
        meta = {'successful': 1, 'failed': 2, 'test_results_count': 3}
        event = record_audit_event(
            course=self.course, event_type='autograder_failed',
            user=self.user, assignment=self.assignment, submission=self.submission, meta=meta,
        )
        self._assert_event(event, 'autograder_failed', self.user, self.assignment, self.submission, meta)

    def test_late_day_used(self):
        meta = {'credits_used': 2}
        event = record_audit_event(
            course=self.course, event_type='late_day_used',
            user=self.user, assignment=self.assignment, submission=self.submission, meta=meta,
        )
        self._assert_event(event, 'late_day_used', self.user, self.assignment, self.submission, meta)

    def test_comment_feedback(self):
        meta = {'comment_id': 42, 'feedback': 1}
        event = record_audit_event(
            course=self.course, event_type='comment_feedback',
            user=self.user, assignment=self.assignment, submission=self.submission, meta=meta,
        )
        self._assert_event(event, 'comment_feedback', self.user, self.assignment, self.submission, meta)

    def test_event_without_optional_fields(self):
        """record_audit_event works with only course + event_type."""
        event = record_audit_event(course=self.course, event_type='submission_attempt')
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, 'submission_attempt')
        self.assertIsNone(event.user)
        self.assertIsNone(event.assignment)
        self.assertIsNone(event.submission)
        self.assertIsNone(event.meta)

    def test_dedup_only_applies_to_file_view_and_feedback_view(self):
        """Non-dedup event types always create a new record."""
        for _ in range(3):
            record_audit_event(
                course=self.course, event_type='submission_attempt',
                user=self.user, submission=self.submission,
            )
        count = CourseAuditEvent.objects.filter(
            course=self.course, event_type='submission_attempt',
        ).count()
        self.assertEqual(count, 3)

    def test_file_view_dedup_within_window(self):
        """file_view is deduplicated per user/submission within 5 min."""
        event1 = record_audit_event(
            course=self.course, event_type='file_view',
            user=self.user, submission=self.submission,
        )
        event2 = record_audit_event(
            course=self.course, event_type='file_view',
            user=self.user, submission=self.submission,
        )
        self.assertIsNotNone(event1)
        self.assertIsNone(event2)

    def test_feedback_view_dedup_within_window(self):
        """feedback_view is deduplicated per user/submission within 5 min."""
        event1 = record_audit_event(
            course=self.course, event_type='feedback_view',
            user=self.user, submission=self.submission,
        )
        event2 = record_audit_event(
            course=self.course, event_type='feedback_view',
            user=self.user, submission=self.submission,
        )
        self.assertIsNotNone(event1)
        self.assertIsNone(event2)

    def _assert_quiz_event(self, event_type):
        event = record_audit_event(
            course=self.course, event_type=event_type,
            user=self.user, quiz=self.quiz, meta={'title': self.quiz.title},
        )
        self._assert_event(event, event_type, self.user)
        self.assertEqual(event.quiz_id, self.quiz.id)

    def test_quiz_created(self):
        self._assert_quiz_event('quiz_created')

    def test_quiz_updated(self):
        self._assert_quiz_event('quiz_updated')

    def test_quiz_published(self):
        self._assert_quiz_event('quiz_published')

    def test_quiz_unpublished(self):
        self._assert_quiz_event('quiz_unpublished')

    def test_quiz_deleted(self):
        self._assert_quiz_event('quiz_deleted')

    def test_quiz_access_code_changed(self):
        self._assert_quiz_event('quiz_access_code_changed')

    def test_quiz_attempt_started(self):
        self._assert_quiz_event('quiz_attempt_started')

    def test_quiz_attempt_started_late(self):
        self._assert_quiz_event('quiz_attempt_started_late')

    def test_quiz_attempt_submitted(self):
        self._assert_quiz_event('quiz_attempt_submitted')

    def test_quiz_attempt_autosubmitted(self):
        self._assert_quiz_event('quiz_attempt_autosubmitted')

    def test_quiz_attempt_seb_blocked(self):
        self._assert_quiz_event('quiz_attempt_seb_blocked')

    def test_quiz_attempts_reset(self):
        self._assert_quiz_event('quiz_attempts_reset')

    def test_quiz_response_graded(self):
        self._assert_quiz_event('quiz_response_graded')

    def test_quiz_response_grade_reopened(self):
        self._assert_quiz_event('quiz_response_grade_reopened')

    def test_quiz_generated_set_approved(self):
        self._assert_quiz_event('quiz_generated_set_approved')

    def test_quiz_generated_set_unapproved(self):
        self._assert_quiz_event('quiz_generated_set_unapproved')

    def test_quiz_generated_set_regenerated(self):
        self._assert_quiz_event('quiz_generated_set_regenerated')

    def test_quiz_generated_sets_published(self):
        self._assert_quiz_event('quiz_generated_sets_published')

    def test_assignment_feedback_changed(self):
        event = record_audit_event(
            course=self.course, event_type='assignment_feedback_changed',
            user=self.user, assignment=self.assignment,
            meta={'from': 'hidden', 'to': 'released'},
        )
        self._assert_event(event, 'assignment_feedback_changed', self.user)
        self.assertEqual(event.assignment_id, self.assignment.id)

    def test_assignment_state_changed(self):
        event = record_audit_event(
            course=self.course, event_type='assignment_state_changed',
            user=self.user, assignment=self.assignment,
            meta={'from': 'draft', 'to': 'published'},
        )
        self._assert_event(event, 'assignment_state_changed', self.user)
        self.assertEqual(event.assignment_id, self.assignment.id)
        self.assertEqual(event.meta, {'from': 'draft', 'to': 'published'})

    def test_all_event_types_covered(self):
        """Ensure every EVENT_TYPE_CHOICES value has a dedicated test above."""
        defined_types = {choice[0] for choice in CourseAuditEvent.EVENT_TYPE_CHOICES}
        tested_types = {
            'submission_attempt', 'submission_failed',
            'file_view', 'feedback_view',
            'regrade_request', 'regrade_deleted',
            'autograder_triggered', 'autograder_completed', 'autograder_failed',
            'late_day_used', 'comment_feedback',
            'assignment_state_changed', 'assignment_feedback_changed',
            'quiz_created', 'quiz_updated', 'quiz_published', 'quiz_unpublished', 'quiz_deleted',
            'quiz_access_code_changed',
            'quiz_attempt_started', 'quiz_attempt_started_late',
            'quiz_attempt_submitted', 'quiz_attempt_autosubmitted', 'quiz_attempt_seb_blocked',
            'quiz_attempts_reset', 'quiz_response_graded', 'quiz_response_grade_reopened',
            'quiz_generated_set_approved', 'quiz_generated_set_unapproved',
            'quiz_generated_set_regenerated',
            'quiz_generated_sets_published',
        }
        self.assertEqual(defined_types, tested_types,
                         f"Untested event types: {defined_types - tested_types}")


# ===========================================================================
# Integration tests: verify API endpoints trigger audit events
# ===========================================================================

class _AuditIntegrationBase(APITestCase):
    """Shared setup: org, admin, student, grader, course, assignment."""

    def setUp(self):
        self.org = OrganizationFactory(name="AuditIntOrg", shortname="AIO")

        self.admin = UserFactory(username="aint_admin", email="admin@aio.edu")
        self.admin.profile.organization = self.org
        self.admin.profile.canCreateCourses = True
        self.admin.profile.canModifyRosters = True
        self.admin.save()

        self.student = UserFactory(username="aint_student", email="student@aio.edu")
        self.student.profile.organization = self.org
        self.student.save()

        self.grader = UserFactory(username="aint_grader", email="grader@aio.edu")
        self.grader.profile.organization = self.org
        self.grader.save()

        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/courses/', {"name": "AuditInt", "period": "S2026"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.course_id = resp.data['id']

        resp = self.client.patch(f'/courses/{self.course_id}/roster/', {
            "students": [self.student.email],
            "graders": [self.grader.email],
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        resp = self.client.post('/assignments/', {
            "name": "AuditHW", "points": 100, "course": self.course_id,
            "state": "published", "allowStudentUpload": True, "allowRegradeRequests": True,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assignment_id = resp.data['id']

    def _upload_submission(self):
        """Upload a submission via studentUpload. Returns submission id."""
        self.client.force_authenticate(user=self.student)
        resp = self.client.post(
            f'/assignments/{self.assignment_id}/studentUpload/',
            {"files": [{"name": "main.py", "data": "print('hello')", "extension": ".py", "path": ""}]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data['id']


class TestStudentUploadAudit(_AuditIntegrationBase):
    def test_student_upload_records_submission_attempt(self):
        sub_id = self._upload_submission()
        events = CourseAuditEvent.objects.filter(course_id=self.course_id, event_type='submission_attempt')
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(event.assignment_id, self.assignment_id)
        self.assertEqual(event.submission_id, sub_id)
        self.assertEqual(event.user, self.student)


class TestCheckPermissionAudit(_AuditIntegrationBase):
    def test_records_file_view_for_student(self):
        sub_id = self._upload_submission()
        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f'/submissions/{sub_id}/checkPermission/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        events = CourseAuditEvent.objects.filter(
            course_id=self.course_id, event_type='file_view',
            submission_id=sub_id, user=self.student,
        )
        self.assertEqual(events.count(), 1)

    def test_records_feedback_view_for_finalized(self):
        sub_id = self._upload_submission()
        # Set feedbackReleased so student gets feedback_view instead of file_view
        Assignment.objects.filter(id=self.assignment_id).update(feedbackStatus='released')
        # Finalize directly in DB to avoid email template rendering (staticfiles)
        Submission.objects.filter(id=sub_id).update(isFinalized=True)

        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f'/submissions/{sub_id}/checkPermission/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        events = CourseAuditEvent.objects.filter(
            course_id=self.course_id, event_type='feedback_view',
            submission_id=sub_id, user=self.student,
        )
        self.assertEqual(events.count(), 1)


class TestRegradeAudit(_AuditIntegrationBase):
    def _setup_finalized_sub(self):
        sub_id = self._upload_submission()
        Submission.objects.filter(id=sub_id).update(isFinalized=True)
        return sub_id

    def test_submit_regrade_records_regrade_request(self):
        sub_id = self._setup_finalized_sub()
        self.client.force_authenticate(user=self.student)
        resp = self.client.patch(f'/submissions/{sub_id}/submitRegrade/', {
            "questionText": "Please re-check problem 3",
            "questionIsRegrade": True,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        events = CourseAuditEvent.objects.filter(
            course_id=self.course_id, event_type='regrade_request',
            submission_id=sub_id, user=self.student,
        )
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(event.meta['questionText'], "Please re-check problem 3")
        self.assertTrue(event.meta['isRegrade'])

    def test_delete_regrade_records_regrade_deleted(self):
        sub_id = self._setup_finalized_sub()
        self.client.force_authenticate(user=self.student)
        self.client.patch(f'/submissions/{sub_id}/submitRegrade/', {
            "questionText": "Please re-check", "questionIsRegrade": False,
        })
        resp = self.client.patch(f'/submissions/{sub_id}/deleteRegrade/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        events = CourseAuditEvent.objects.filter(
            course_id=self.course_id, event_type='regrade_deleted',
            submission_id=sub_id, user=self.student,
        )
        self.assertEqual(events.count(), 1)


class TestCommentFeedbackAudit(_AuditIntegrationBase):
    def test_comment_feedback_records_audit(self):
        sub_id = self._upload_submission()

        # Grader must claim submission before commenting
        self.client.force_authenticate(user=self.grader)
        resp = self.client.get(f'/assignments/{self.assignment_id}/drawUnassigned/?amount=1')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        # Use the file created by studentUpload
        submission = Submission.objects.get(id=sub_id)
        file_id = submission.files.first().id

        resp = self.client.post('/comments/', {
            "text": "Good work!", "pointDelta": 0,
            "startLine": 1, "endLine": 1, "startChar": 0, "endChar": 5,
            "file": file_id, "author": self.grader.email,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        comment_id = resp.data['id']

        Submission.objects.filter(id=sub_id).update(isFinalized=True)

        self.client.force_authenticate(user=self.student)
        resp = self.client.patch(f'/comments/{comment_id}/feedback/', {"feedback": 1})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        events = CourseAuditEvent.objects.filter(
            course_id=self.course_id, event_type='comment_feedback', user=self.student,
        )
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(event.meta['comment_id'], comment_id)
        self.assertEqual(event.meta['feedback'], 1)


# ===========================================================================
# Autograder audit: use real DB objects, mock only Executor and Builder
# ===========================================================================

class TestAutograderAuditPaths(TransactionTestCase):
    """Verify that RunSubmission records autograder audit events.

    Uses real DB objects for Submission/Assignment/Course so record_audit_event
    can write CourseAuditEvent rows. Only mocks the Executor (to avoid Docker).
    """

    def setUp(self):
        from core.models import Organization, Course, User
        Organization.objects.filter(name="AG Audit Org").delete()

        self.org = Organization.objects.create(name="AG Audit Org", shortname="AGAO")
        self.course = Course.objects.create(name="AG Audit Course", period="S2026", organization=self.org)
        self.assignment = Assignment.objects.create(name="AG HW", course=self.course, points=100)
        self.env = Environment.objects.create(
            assignment=self.assignment,
            language="python-3.12",
            requirements="",
            image_name="codepost-env-test-v1",
            current_build_version=1,
        )
        self.student = User.objects.create(username="ag_student", email="ag_student@agao.edu")
        self.submission = Submission.objects.create(assignment=self.assignment)
        self.submission.students.add(self.student)
        self.sub_file = SubmissionFile.objects.create(
            submission=self.submission, name="main.py", extension=".py",
            data="print('hello')",
        )

    def tearDown(self):
        self.sub_file.delete()
        self.submission.delete()
        self.env.delete()
        self.assignment.delete()
        self.course.delete()
        self.org.delete()
        self.student.delete()

    @patch('autograder.run.Executor.factory')
    def test_triggered_and_completed_on_success(self, mock_executor_factory):
        """RunSubmission records autograder_triggered and autograder_completed."""
        from autograder.services.executors import ExecutionResult

        mock_executor = MagicMock()
        mock_result = ExecutionResult(success=True, stdout="hello", stderr="", execution_time=0.1)
        mock_executor.execute.return_value = mock_result
        mock_executor_factory.return_value = mock_executor

        CourseAuditEvent.objects.filter(course=self.course).delete()

        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            from autograder.run import RunSubmission
            RunSubmission.apply(args=[self.submission.id])

        triggered = CourseAuditEvent.objects.filter(course=self.course, event_type='autograder_triggered')
        self.assertEqual(triggered.count(), 1)
        self.assertEqual(triggered.first().user, self.student)
        self.assertEqual(triggered.first().submission, self.submission)

        completed = CourseAuditEvent.objects.filter(course=self.course, event_type='autograder_completed')
        self.assertEqual(completed.count(), 1)
        self.assertEqual(completed.first().meta['successful'], 1)

    @patch('autograder.run.Executor.factory')
    def test_triggered_and_failed_on_execution_error(self, mock_executor_factory):
        """RunSubmission records autograder_triggered and autograder_failed when execution fails."""
        mock_executor = MagicMock()
        mock_executor.execute.side_effect = Exception("Execution failed")
        mock_executor_factory.return_value = mock_executor

        CourseAuditEvent.objects.filter(course=self.course).delete()

        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            from autograder.run import RunSubmission
            RunSubmission.apply(args=[self.submission.id])

        triggered = CourseAuditEvent.objects.filter(course=self.course, event_type='autograder_triggered')
        self.assertEqual(triggered.count(), 1)

        failed = CourseAuditEvent.objects.filter(course=self.course, event_type='autograder_failed')
        self.assertEqual(failed.count(), 1)
        event = failed.first()
        self.assertIn('failed', event.meta)
        self.assertGreater(event.meta['failed'], 0)

        completed = CourseAuditEvent.objects.filter(course=self.course, event_type='autograder_completed')
        self.assertEqual(completed.count(), 0)
