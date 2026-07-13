# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Robust tests for TestCategory, TestCase, and SubmissionTest models.

Covers:
- TestCategory unique_together (name, assignment)
- TestCase types and point values
- SubmissionTest pass/fail/error states
- Course property traversal
- Cascade delete from assignment
"""
from decimal import Decimal
from django.test import TestCase as DjangoTestCase
from django.db import IntegrityError

from core.models import (
    Assignment, Course, Submission, TestCategory, TestCase, SubmissionTest,
)
from core.tests.factories import OrganizationFactory


class TestTestCategoryModel(DjangoTestCase):
    """TestCategory constraints and behavior."""

    def setUp(self):
        self.org = OrganizationFactory(name="TCOrg1", shortname="tco1")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(course=self.course, name="HW1", points=20)

    def test_unique_together_name_assignment(self):
        TestCategory.objects.create(assignment=self.assignment, name="Unit Tests")
        with self.assertRaises(IntegrityError):
            TestCategory.objects.create(assignment=self.assignment, name="Unit Tests")

    def test_same_name_different_assignment_ok(self):
        a2 = Assignment.objects.create(course=self.course, name="HW2", points=20)
        tc1 = TestCategory.objects.create(assignment=self.assignment, name="Unit Tests")
        tc2 = TestCategory.objects.create(assignment=a2, name="Unit Tests")
        self.assertNotEqual(tc1.pk, tc2.pk)

    def test_course_property(self):
        tc = TestCategory.objects.create(assignment=self.assignment, name="IO Tests")
        self.assertEqual(tc.course, self.course)

    def test_defaults(self):
        tc = TestCategory.objects.create(assignment=self.assignment, name="Tests")
        self.assertEqual(tc.maxPoints, 0)
        self.assertEqual(tc.sortKey, 0)
        self.assertEqual(tc.testScript, "")

    def test_cascade_delete_from_assignment(self):
        tc = TestCategory.objects.create(assignment=self.assignment, name="Tests")
        tc_id = tc.pk
        self.assignment.delete()
        self.assertFalse(TestCategory.objects.filter(pk=tc_id).exists())


class TestTestCaseModel(DjangoTestCase):
    """TestCase types and fields."""

    def setUp(self):
        self.org = OrganizationFactory(name="TCOrg2", shortname="tco2")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(course=self.course, name="HW1", points=20)
        self.category = TestCategory.objects.create(assignment=self.assignment, name="Tests")

    def test_io_type(self):
        tc = TestCase.objects.create(
            testCategory=self.category, description="Test IO",
            type="io", pointsFail=0, pointsPass=5,
        )
        self.assertEqual(tc.type, "io")

    def test_unit_type(self):
        tc = TestCase.objects.create(
            testCategory=self.category, description="Test Unit",
            type="unit", pointsFail=0, pointsPass=10,
        )
        self.assertEqual(tc.type, "unit")

    def test_script_type(self):
        tc = TestCase.objects.create(
            testCategory=self.category, description="Script Test",
            type="script", pointsFail=0, pointsPass=5,
            testCode="assert True",
        )
        self.assertEqual(tc.testCode, "assert True")

    def test_exposed_default_false(self):
        tc = TestCase.objects.create(
            testCategory=self.category, description="Test",
            type="io", pointsFail=0, pointsPass=5,
        )
        self.assertFalse(tc.exposed)

    def test_timeout_default(self):
        tc = TestCase.objects.create(
            testCategory=self.category, description="Test",
            type="io", pointsFail=0, pointsPass=5,
        )
        self.assertEqual(tc.timeout, 30)

    def test_course_property(self):
        tc = TestCase.objects.create(
            testCategory=self.category, description="Test",
            type="io", pointsFail=0, pointsPass=5,
        )
        self.assertEqual(tc.course, self.course)

    def test_cascade_from_category(self):
        tc = TestCase.objects.create(
            testCategory=self.category, description="Test",
            type="io", pointsFail=0, pointsPass=5,
        )
        tc_id = tc.pk
        self.category.delete()
        self.assertFalse(TestCase.objects.filter(pk=tc_id).exists())


class TestSubmissionTestModel(DjangoTestCase):
    """SubmissionTest pass/fail tracking."""

    def setUp(self):
        self.org = OrganizationFactory(name="TCOrg3", shortname="tco3")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(course=self.course, name="HW1", points=20)
        self.submission = Submission.objects.create(assignment=self.assignment)
        self.category = TestCategory.objects.create(assignment=self.assignment, name="Tests")
        self.test_case = TestCase.objects.create(
            testCategory=self.category, description="Test",
            type="io", pointsFail=0, pointsPass=5,
        )

    def test_passed_test(self):
        st = SubmissionTest.objects.create(
            submission=self.submission, testCase=self.test_case,
            logs="All good", passed=True,
        )
        self.assertTrue(st.passed)
        self.assertFalse(st.isError)

    def test_failed_test(self):
        st = SubmissionTest.objects.create(
            submission=self.submission, testCase=self.test_case,
            logs="Expected 5, got 3", passed=False,
        )
        self.assertFalse(st.passed)

    def test_error_test(self):
        st = SubmissionTest.objects.create(
            submission=self.submission, testCase=self.test_case,
            logs="RuntimeError", passed=False, isError=True,
        )
        self.assertTrue(st.isError)

    def test_score_fields(self):
        st = SubmissionTest.objects.create(
            submission=self.submission, testCase=self.test_case,
            logs="", passed=True, score=Decimal("4.50"), maxScore=Decimal("5.00"),
        )
        self.assertEqual(st.score, Decimal("4.50"))
        self.assertEqual(st.maxScore, Decimal("5.00"))

    def test_course_property(self):
        st = SubmissionTest.objects.create(
            submission=self.submission, testCase=self.test_case,
            logs="", passed=True,
        )
        self.assertEqual(st.course, self.course)

    def test_cascade_from_submission(self):
        st = SubmissionTest.objects.create(
            submission=self.submission, testCase=self.test_case,
            logs="", passed=True,
        )
        st_id = st.pk
        self.submission.delete()
        self.assertFalse(SubmissionTest.objects.filter(pk=st_id).exists())
