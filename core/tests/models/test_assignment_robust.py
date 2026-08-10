# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Robust tests for Assignment model.

Covers:
- unique_together (name, course)
- calculate_average_and_median
- Additive vs deductive grading defaults
- Sort key ordering
- Cascade from Course
- Various settings defaults
"""
from decimal import Decimal
from django.test import TestCase
from django.db import IntegrityError

from core.models import Assignment, Course, Submission, RubricCategory
from core.tests.factories import OrganizationFactory


class TestAssignmentModelConstraints(TestCase):
    """unique_together and meta."""

    def setUp(self):
        self.org = OrganizationFactory(name="AsgOrg1", shortname="ao1")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)

    def test_unique_together_name_course(self):
        Assignment.objects.create(name="HW1", points=10, course=self.course)
        with self.assertRaises(IntegrityError):
            Assignment.objects.create(name="HW1", points=20, course=self.course)

    def test_same_name_different_course_ok(self):
        course2 = Course.objects.create(name="CS201", period="F2020", organization=self.org)
        a1 = Assignment.objects.create(name="HW1", points=10, course=self.course)
        a2 = Assignment.objects.create(name="HW1", points=10, course=course2)
        self.assertNotEqual(a1.pk, a2.pk)

    def test_ordering_by_sortkey_then_name(self):
        Assignment.objects.create(name="Zebra", points=10, course=self.course, sortKey=2)
        Assignment.objects.create(name="Alpha", points=10, course=self.course, sortKey=1)
        Assignment.objects.create(name="Beta", points=10, course=self.course, sortKey=1)
        assignments = list(Assignment.objects.filter(course=self.course))
        names = [a.name for a in assignments]
        self.assertEqual(names, ["Alpha", "Beta", "Zebra"])

    def test_str_includes_name_and_course(self):
        a = Assignment.objects.create(name="Loops", points=20, course=self.course)
        self.assertIn("Loops", str(a))
        self.assertIn("CS101", str(a))


class TestAssignmentDefaults(TestCase):
    """Default field values."""

    def setUp(self):
        self.org = OrganizationFactory(name="AsgOrg2", shortname="ao2")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)

    def test_additive_grading_defaults_false(self):
        a = Assignment.objects.create(name="HW1", points=20, course=self.course)
        self.assertFalse(a.additiveGrading)

    def test_is_released_defaults_false(self):
        a = Assignment.objects.create(name="HW1", points=20, course=self.course)
        self.assertEqual(a.state, 'draft')

    def test_anonymous_grading_defaults_false(self):
        a = Assignment.objects.create(name="HW1", points=20, course=self.course)
        self.assertFalse(a.anonymousGrading)

    def test_forced_rubric_mode_defaults_false(self):
        a = Assignment.objects.create(name="HW1", points=20, course=self.course)
        self.assertFalse(a.forcedRubricMode)

    def test_template_mode_defaults_false(self):
        a = Assignment.objects.create(name="HW1", points=20, course=self.course)
        self.assertFalse(a.templateMode)

    def test_feedback_released_defaults_false(self):
        a = Assignment.objects.create(name="HW1", points=20, course=self.course)
        self.assertFalse(a.feedbackReleased)

    def test_sort_key_defaults_zero(self):
        a = Assignment.objects.create(name="HW1", points=20, course=self.course)
        self.assertEqual(a.sortKey, 0)

    def test_points_stored_as_decimal(self):
        a = Assignment.objects.create(name="HW1", points=Decimal("15.50"), course=self.course)
        a.refresh_from_db()
        self.assertEqual(a.points, Decimal("15.50"))


class TestAssignmentAverageMedian(TestCase):
    """calculate_average_and_median behavior."""

    def setUp(self):
        self.org = OrganizationFactory(name="AsgOrg3", shortname="ao3")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(name="HW1", points=20, course=self.course)

    def test_no_submissions_returns_none(self):
        mean, median = self.assignment.calculate_average_and_median()
        self.assertIsNone(mean)
        self.assertIsNone(median)

    def test_with_finalized_submissions(self):
        _s1 = Submission.objects.create(assignment=self.assignment, isFinalized=True, grade=Decimal("10"), gradeFrozen=True)
        _s2 = Submission.objects.create(assignment=self.assignment, isFinalized=True, grade=Decimal("20"), gradeFrozen=True)
        _s3 = Submission.objects.create(assignment=self.assignment, isFinalized=True, grade=Decimal("15"), gradeFrozen=True)
        mean, median = self.assignment.calculate_average_and_median()
        self.assertIsNotNone(mean)
        self.assertAlmostEqual(float(mean), 15.0, places=1)

    def test_unfinalized_not_included(self):
        Submission.objects.create(assignment=self.assignment, isFinalized=False, grade=Decimal("0"), gradeFrozen=True)
        Submission.objects.create(assignment=self.assignment, isFinalized=True, grade=Decimal("18"), gradeFrozen=True)
        mean, median = self.assignment.calculate_average_and_median()
        self.assertIsNotNone(mean)
        # Only the one finalized submission counts
        self.assertAlmostEqual(float(mean), 18.0, places=1)


class TestAssignmentCascade(TestCase):
    """Cascade delete behavior."""

    def setUp(self):
        self.org = OrganizationFactory(name="AsgOrg4", shortname="ao4")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)

    def test_delete_course_cascades_assignments(self):
        Assignment.objects.create(name="HW1", points=10, course=self.course)
        Assignment.objects.create(name="HW2", points=10, course=self.course)
        course_id = self.course.pk
        self.course.delete()
        self.assertEqual(Assignment.objects.filter(course_id=course_id).count(), 0)

    def test_delete_assignment_cascades_rubric(self):
        a = Assignment.objects.create(name="HW1", points=10, course=self.course)
        RubricCategory.objects.create(assignment=a, name="General")
        a_id = a.pk
        a.delete()
        self.assertEqual(RubricCategory.objects.filter(assignment_id=a_id).count(), 0)
