# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from rest_framework.test import APITestCase
from rest_framework import status
from core.models import CourseAuditEvent
from core.services.audit import record_audit_event
from core.tests.factories import OrganizationFactory, UserFactory


class TestCourseAuditLog(APITestCase):
    """Tests for the course audit log feature."""

    def setUp(self):
        self.org = OrganizationFactory(name="Audit Org", shortname="AO")

        self.admin = UserFactory(username="audit_admin", email="admin@ao.edu")
        self.admin.profile.organization = self.org
        self.admin.profile.canCreateCourses = True
        self.admin.profile.canModifyRosters = True
        self.admin.save()

        self.student = UserFactory(username="audit_student", email="student@ao.edu")
        self.student.profile.organization = self.org
        self.student.save()

        self.other_user = UserFactory(username="audit_other", email="other@ao.edu")
        self.other_user.profile.organization = self.org
        self.other_user.save()

        # Create course
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/courses/', {"name": "Audit Course", "period": "S2026"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.course_id = response.data['id']

        # Add student to roster
        response = self.client.patch(f'/courses/{self.course_id}/roster/', {
            "students": [self.student.email],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Create assignment
        response = self.client.post('/assignments/', {
            "name": "Audit HW",
            "points": 100,
            "course": self.course_id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assignment_id = response.data['id']

    def test_record_audit_event_creates_event(self):
        """record_audit_event() creates a CourseAuditEvent record."""
        from core.models import Course, Assignment
        course = Course.objects.get(id=self.course_id)
        assignment = Assignment.objects.get(id=self.assignment_id)

        event = record_audit_event(
            course=course,
            event_type='submission_attempt',
            user=self.student,
            assignment=assignment,
            meta={'test': True},
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, 'submission_attempt')
        self.assertEqual(event.course_id, self.course_id)
        self.assertEqual(event.user_id, self.student.id)
        self.assertEqual(event.meta, {'test': True})

    def test_deduplication_file_view(self):
        """file_view events are deduplicated within 5 minutes per user/submission."""
        from core.models import Course, Submission
        course = Course.objects.get(id=self.course_id)
        submission = Submission.objects.filter(assignment_id=self.assignment_id).first()
        if not submission:
            self.skipTest("No submission to test dedup with")

        event1 = record_audit_event(
            course=course, event_type='file_view',
            user=self.student, submission=submission,
        )
        event2 = record_audit_event(
            course=course, event_type='file_view',
            user=self.student, submission=submission,
        )
        self.assertIsNotNone(event1)
        self.assertIsNone(event2)  # deduped

    def test_audit_log_endpoint_returns_events(self):
        """GET /courses/{id}/auditLog/ returns audit events for course admins."""
        from core.models import Course, Assignment
        course = Course.objects.get(id=self.course_id)
        assignment = Assignment.objects.get(id=self.assignment_id)

        record_audit_event(course=course, event_type='submission_attempt', user=self.student, assignment=assignment)
        record_audit_event(course=course, event_type='feedback_view', user=self.student, assignment=assignment)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/courses/{self.course_id}/auditLog/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Paginated response
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)

    def test_audit_log_filter_by_event_type(self):
        """Audit log can be filtered by event_type."""
        from core.models import Course, Assignment
        course = Course.objects.get(id=self.course_id)
        assignment = Assignment.objects.get(id=self.assignment_id)

        record_audit_event(course=course, event_type='submission_attempt', user=self.student, assignment=assignment)
        record_audit_event(course=course, event_type='feedback_view', user=self.student, assignment=assignment)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/courses/{self.course_id}/auditLog/', {'event_type': 'submission_attempt'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['eventType'], 'submission_attempt')

    def test_audit_log_filter_by_student(self):
        """Audit log can be filtered by student email."""
        from core.models import Course, Assignment
        course = Course.objects.get(id=self.course_id)
        assignment = Assignment.objects.get(id=self.assignment_id)

        record_audit_event(course=course, event_type='submission_attempt', user=self.student, assignment=assignment)
        record_audit_event(course=course, event_type='submission_attempt', user=self.admin, assignment=assignment)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/courses/{self.course_id}/auditLog/', {'student': self.student.email})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['userEmail'], self.student.email)

    def test_audit_log_forbidden_for_non_admin(self):
        """Non-admin users get 403 on the audit log endpoint."""
        self.client.force_authenticate(user=self.student)
        response = self.client.get(f'/courses/{self.course_id}/auditLog/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_audit_log_export_csv(self):
        """GET /courses/{id}/auditLogExport/ returns CSV content."""
        from core.models import Course, Assignment
        course = Course.objects.get(id=self.course_id)
        assignment = Assignment.objects.get(id=self.assignment_id)

        record_audit_event(course=course, event_type='submission_attempt', user=self.student, assignment=assignment)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/courses/{self.course_id}/auditLogExport/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode('utf-8')
        self.assertIn('Timestamp', content)
        self.assertIn('submission_attempt', content)
        self.assertIn(self.student.email, content)

    def test_audit_log_export_forbidden_for_non_admin(self):
        """Non-admin users get 403 on the audit log export endpoint."""
        self.client.force_authenticate(user=self.student)
        response = self.client.get(f'/courses/{self.course_id}/auditLogExport/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
