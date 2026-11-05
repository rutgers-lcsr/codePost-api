# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
GET /submissions/{id}/testResults/ `logs`: the contents of the dumpMode `_tests.txt`
SubmissionFile. Staff get it; a student only once grading results are revealed, and never
when the dump would contain hidden-test output.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import (
    Assignment,
    Course,
    Organization,
    Submission,
    SubmissionFile,
    SubmissionTest,
    TestCase as AutograderTestCase,
    TestCategory,
)


class TestResultsDumpLogsTests(APITestCase):
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
        SubmissionFile.objects.create(
            submission=self.submission, name="_tests.txt", extension=".txt",
            data="DUMPLOGS", path="", hiddenBeforePublish=True)

    def _add_test(self, hidden):
        tc = AutograderTestCase.objects.create(
            testCategory=self.category, functionName="t", description="t",
            pointsPass=2, exposed=True, hidden=hidden)
        SubmissionTest.objects.create(
            submission=self.submission, testCase=tc, logs="x", passed=True,
            score=Decimal("2"), maxScore=Decimal("2"))

    def _release(self):
        Assignment.objects.filter(id=self.assignment.id).update(feedbackStatus='released')
        Submission.objects.filter(id=self.submission.id).update(isFinalized=True)

    def _logs(self, user, query=""):
        self.client.force_authenticate(user=user)
        resp = self.client.get(f"/submissions/{self.submission.id}/testResults/{query}")
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()["logs"]

    def test_staff_gets_dump_logs(self):
        self.assertEqual(self._logs(self.admin), "DUMPLOGS")

    def test_student_does_not_get_dump_before_release(self):
        self.assertEqual(self._logs(self.student), "")

    def test_student_gets_dump_after_release(self):
        self._add_test(hidden=False)
        self._release()
        self.assertEqual(self._logs(self.student), "DUMPLOGS")

    def test_student_never_gets_dump_that_contains_hidden_test_output(self):
        self._add_test(hidden=True)
        self._release()
        self.assertEqual(self._logs(self.student), "")
