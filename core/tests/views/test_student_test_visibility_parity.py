# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Every student-facing route that exposes SubmissionTests must apply the same rules:
TestCase.exposed / maxExposedFailedTests until grading results are revealed, and
TestCase.hidden always (students only ever get a per-category pass/fail + points summary).

Routes covered: GET /submissionTests/{id}/ and GET /submissions/{id}/submissionTests/.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import (
    Assignment,
    Course,
    Organization,
    Submission,
    SubmissionTest,
    TestCase as AutograderTestCase,
    TestCategory,
)


class StudentTestVisibilityParityTests(APITestCase):
    def setUp(self):
        org = Organization.objects.create(name="Org", shortname="org")
        self.student = User.objects.create_user("student@org.edu", "student@org.edu", "pw")
        self.admin = User.objects.create_user("admin@org.edu", "admin@org.edu", "pw")
        self.course = Course.objects.create(name="cs101", period="s2026", organization=org)
        self.course.courseAdmins.add(self.admin)
        self.course.students.add(self.student)
        self.assignment = Assignment.objects.create(
            course=self.course, name="A1", points=20, state='published')
        self.category = TestCategory.objects.create(name="Cat", assignment=self.assignment)
        self.submission = Submission.objects.create(assignment=self.assignment, isFinalized=False)
        self.submission.students.add(self.student)

    def _add_test(self, name, logs, exposed, hidden, passed=False):
        tc = AutograderTestCase.objects.create(
            testCategory=self.category, functionName=name, description=name,
            pointsPass=2, exposed=exposed, hidden=hidden)
        return SubmissionTest.objects.create(
            submission=self.submission, testCase=tc, logs=logs, passed=passed,
            score=Decimal("2") if passed else Decimal("0"), maxScore=Decimal("2"))

    def _release(self):
        Assignment.objects.filter(id=self.assignment.id).update(feedbackStatus='released')
        Submission.objects.filter(id=self.submission.id).update(isFinalized=True)

    # --- GET /submissionTests/{id}/ ---------------------------------------

    def test_student_cannot_read_unexposed_test_directly(self):
        st = self._add_test("t_secret", "SECRET LOGS", exposed=False, hidden=False)
        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f"/submissionTests/{st.id}/")
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertNotIn("SECRET LOGS", resp.content.decode())

    def test_student_can_read_exposed_test_directly(self):
        st = self._add_test("t_open", "OPEN LOGS", exposed=True, hidden=False)
        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f"/submissionTests/{st.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["logs"], "OPEN LOGS")

    def test_student_reads_unexposed_test_directly_after_release(self):
        st = self._add_test("t_secret", "RELEASED LOGS", exposed=False, hidden=False)
        self._release()
        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f"/submissionTests/{st.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_student_cannot_read_hidden_test_directly_even_after_release(self):
        st = self._add_test("t_hidden", "HIDDENLOGS", exposed=True, hidden=True)
        self._release()
        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f"/submissionTests/{st.id}/")
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_admin_reads_unexposed_test_directly(self):
        st = self._add_test("t_secret", "SECRET LOGS", exposed=False, hidden=False)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f"/submissionTests/{st.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)

    # --- GET /submissions/{id}/submissionTests/ ---------------------------

    def test_submission_tests_action_masks_hidden_tests_for_student(self):
        self._add_test("t_open", "OPEN LOGS", exposed=True, hidden=False, passed=True)
        hidden = self._add_test("t_hidden", "HIDDENLOGS", exposed=True, hidden=True)
        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f"/submissions/{self.submission.id}/submissionTests/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertNotIn("HIDDENLOGS", resp.content.decode())
        rows = resp.json()
        self.assertNotIn(hidden.testCase_id, [r["testCase"] for r in rows])
        summaries = [r for r in rows if r.get("hiddenSummary")]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["hiddenSummary"]["totalCount"], 1)
        self.assertEqual(summaries[0]["hiddenSummary"]["passedCount"], 0)

    def test_submission_tests_action_masks_hidden_tests_after_release(self):
        self._add_test("t_open", "OPEN LOGS", exposed=False, hidden=False, passed=True)
        self._add_test("t_hidden", "HIDDENLOGS", exposed=False, hidden=True)
        self._release()
        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f"/submissions/{self.submission.id}/submissionTests/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertNotIn("HIDDENLOGS", resp.content.decode())
        self.assertIn("OPEN LOGS", resp.content.decode())

    def test_submission_tests_action_staff_still_sees_everything(self):
        self._add_test("t_hidden", "HIDDENLOGS", exposed=False, hidden=True)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f"/submissions/{self.submission.id}/submissionTests/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("HIDDENLOGS", resp.content.decode())
