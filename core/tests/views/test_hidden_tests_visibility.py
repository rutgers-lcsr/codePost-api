# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Confirms the role-based visibility contract for hidden tests:

- Course admins (instructors) see hidden tests in the assignment test-case listing
  and full details in submissionTestResults.
- Graders see hidden tests in the assignment test-case listing and full details in
  submissionTestResults.
- Students never see individual hidden tests. In submissionTestResults they receive
  one synthetic per-category 'Hidden tests' summary that reports the pass count and
  point impact without leaking names, descriptions, or logs.
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


class HiddenTestVisibilityTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Org", shortname="org")

        cls.instructor = User.objects.create_user("inst@org.edu", "inst@org.edu", "pw")
        cls.instructor.profile.organization = cls.org
        cls.instructor.save()

        cls.grader = User.objects.create_user("grader@org.edu", "grader@org.edu", "pw")
        cls.grader.profile.organization = cls.org
        cls.grader.save()

        cls.student = User.objects.create_user("student@org.edu", "student@org.edu", "pw")
        cls.student.profile.organization = cls.org
        cls.student.save()

        cls.course = Course.objects.create(name="cs101", period="s2026", organization=cls.org)
        cls.course.courseAdmins.add(cls.instructor)
        cls.course.graders.add(cls.grader)
        cls.course.students.add(cls.student)

        cls.assignment = Assignment.objects.create(
            course=cls.course,
            name="A1",
            points=20,
            isReleased=True,
        )

        cls.category = TestCategory.objects.create(name="Cat", assignment=cls.assignment)

        cls.visible_test = AutograderTestCase.objects.create(
            testCategory=cls.category,
            functionName="test_visible",
            description="Visible test",
            pointsPass=2,
            hidden=False,
            exposed=True,
        )
        cls.hidden_pass = AutograderTestCase.objects.create(
            testCategory=cls.category,
            functionName="test_hidden_pass",
            description="Secret hidden test (passes)",
            explanation="Internal explanation that students must not see",
            pointsPass=3,
            hidden=True,
            exposed=True,
        )
        cls.hidden_fail = AutograderTestCase.objects.create(
            testCategory=cls.category,
            functionName="test_hidden_fail",
            description="Another hidden test (fails)",
            explanation="More internal-only text",
            pointsPass=2,
            hidden=True,
            exposed=True,
        )

        cls.submission = Submission.objects.create(
            assignment=cls.assignment,
            isFinalized=True,
            grader=cls.grader,
        )
        cls.submission.students.add(cls.student)

        SubmissionTest.objects.create(
            submission=cls.submission,
            testCase=cls.visible_test,
            logs="visible logs",
            passed=True,
            score=Decimal("2"),
            maxScore=Decimal("2"),
        )
        SubmissionTest.objects.create(
            submission=cls.submission,
            testCase=cls.hidden_pass,
            logs="hidden pass logs",
            passed=True,
            score=Decimal("3"),
            maxScore=Decimal("3"),
        )
        SubmissionTest.objects.create(
            submission=cls.submission,
            testCase=cls.hidden_fail,
            logs="hidden fail logs",
            passed=False,
            score=Decimal("0"),
            maxScore=Decimal("2"),
        )

    # ------------------------------------------------------------------
    # /assignments/{id}/testCases/ — listing visibility
    # ------------------------------------------------------------------

    def _list_test_cases_as(self, user):
        self.client.force_authenticate(user=user)
        resp = self.client.get(f"/assignments/{self.assignment.id}/studentTests/")
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()["testCases"]

    def test_instructor_sees_hidden_tests_in_listing(self):
        cases = self._list_test_cases_as(self.instructor)
        ids = {c["id"] for c in cases}
        self.assertIn(self.visible_test.id, ids)
        self.assertIn(self.hidden_pass.id, ids)
        self.assertIn(self.hidden_fail.id, ids)

    def test_grader_sees_hidden_tests_in_listing(self):
        cases = self._list_test_cases_as(self.grader)
        ids = {c["id"] for c in cases}
        self.assertIn(self.hidden_pass.id, ids)
        self.assertIn(self.hidden_fail.id, ids)

    def test_student_does_not_see_hidden_tests_in_listing(self):
        cases = self._list_test_cases_as(self.student)
        ids = {c["id"] for c in cases}
        self.assertIn(self.visible_test.id, ids)
        self.assertNotIn(self.hidden_pass.id, ids)
        self.assertNotIn(self.hidden_fail.id, ids)
        # Belt-and-suspenders: the hidden description/explanation must never appear in
        # a student-facing payload, even smuggled through another field.
        payload = str(cases)
        self.assertNotIn("Secret hidden test", payload)
        self.assertNotIn("Internal explanation", payload)

    # ------------------------------------------------------------------
    # /submissions/{id}/submissionTestResults/ — run visibility
    # ------------------------------------------------------------------

    def _test_results_as(self, user):
        self.client.force_authenticate(user=user)
        resp = self.client.get(f"/submissions/{self.submission.id}/testResults/")
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def test_instructor_sees_full_hidden_test_results(self):
        body = self._test_results_as(self.instructor)
        rows = body["submissionTests"]
        # All three real SubmissionTest rows present; no synthetic summary row.
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r.get("hiddenSummary") is None for r in rows))
        logs = {r["logs"] for r in rows}
        self.assertIn("hidden pass logs", logs)
        self.assertIn("hidden fail logs", logs)

    def test_grader_sees_full_hidden_test_results(self):
        body = self._test_results_as(self.grader)
        rows = body["submissionTests"]
        self.assertEqual(len(rows), 3)
        logs = {r["logs"] for r in rows}
        self.assertIn("hidden pass logs", logs)
        self.assertIn("hidden fail logs", logs)

    def test_student_gets_consolidated_hidden_summary(self):
        body = self._test_results_as(self.student)
        rows = body["submissionTests"]

        # Exactly one visible-test row + one synthetic per-category hidden summary.
        real_rows = [r for r in rows if r.get("hiddenSummary") is None]
        synthetic_rows = [r for r in rows if r.get("hiddenSummary") is not None]
        self.assertEqual(len(real_rows), 1, real_rows)
        self.assertEqual(real_rows[0]["testCase"], self.visible_test.id)
        self.assertEqual(len(synthetic_rows), 1, synthetic_rows)

        summary = synthetic_rows[0]
        self.assertIsNone(summary["testCase"])
        self.assertEqual(summary["testCategory"], self.category.id)
        # 1 of 2 hidden tests passed; 3 of 5 points earned.
        self.assertEqual(summary["hiddenSummary"]["passedCount"], 1)
        self.assertEqual(summary["hiddenSummary"]["totalCount"], 2)
        self.assertEqual(float(summary["hiddenSummary"]["pointsEarned"]), 3.0)
        self.assertEqual(float(summary["hiddenSummary"]["pointsTotal"]), 5.0)
        # Top-level `passed` is False because not all hidden tests passed.
        self.assertFalse(summary["passed"])

        # The student must never see the underlying hidden-test logs/descriptions.
        payload = str(body)
        self.assertNotIn("hidden pass logs", payload)
        self.assertNotIn("hidden fail logs", payload)
        self.assertNotIn("Secret hidden test", payload)
        self.assertNotIn("Internal explanation", payload)

    def test_student_summary_omitted_when_no_hidden_tests_run(self):
        # New submission with only a visible test result.
        sub = Submission.objects.create(assignment=self.assignment, isFinalized=True)
        sub.students.add(self.student)
        SubmissionTest.objects.create(
            submission=sub,
            testCase=self.visible_test,
            logs="x",
            passed=True,
            score=Decimal("2"),
            maxScore=Decimal("2"),
        )
        self.client.force_authenticate(user=self.student)
        body = self.client.get(f"/submissions/{sub.id}/testResults/").json()
        rows = body["submissionTests"]
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].get("hiddenSummary"))
