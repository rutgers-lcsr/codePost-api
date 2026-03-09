# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Robust tests for RubricCategory and RubricComment models.

Covers:
- RubricCategory: pointLimit caps, sortKey, atMostOnce, course property
- RubricComment: pointDelta (positive/negative), sort order, category relationship
- Cascade delete from Assignment
"""
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APITestCase

from core.models import RubricCategory, RubricComment, Assignment, Course
from core.tests.factories import (
    AssignmentFactory, CourseFactory, OrganizationFactory,
    RubricCategoryFactory, RubricCommentFactory,
)
from core.tests.utils import setUpBase, request_as
from core.tests.views.personas import Persona


class TestRubricCategoryModel(TestCase):
    """Model-level behavior for RubricCategory."""

    def setUp(self):
        self.org = OrganizationFactory(name="RubOrg1", shortname="rbo1")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(course=self.course, name="HW1", points=20)

    def test_point_limit_null_means_unlimited(self):
        cat = RubricCategory.objects.create(assignment=self.assignment, name="Style", pointLimit=None)
        self.assertIsNone(cat.pointLimit)

    def test_point_limit_negative_caps_deductions(self):
        cat = RubricCategory.objects.create(assignment=self.assignment, name="Style", pointLimit=-5)
        self.assertEqual(cat.pointLimit, -5)

    def test_at_most_once_default_false(self):
        cat = RubricCategory.objects.create(assignment=self.assignment, name="General")
        self.assertFalse(cat.atMostOnce)

    def test_sort_key_default_zero(self):
        cat = RubricCategory.objects.create(assignment=self.assignment, name="General")
        self.assertEqual(cat.sortKey, 0)

    def test_course_property(self):
        cat = RubricCategory.objects.create(assignment=self.assignment, name="General")
        self.assertEqual(cat.course, self.course)

    def test_cascade_delete_from_assignment(self):
        cat = RubricCategory.objects.create(assignment=self.assignment, name="ToDelete")
        cat_id = cat.pk
        self.assignment.delete()
        self.assertFalse(RubricCategory.objects.filter(pk=cat_id).exists())

    def test_multiple_categories_per_assignment(self):
        RubricCategory.objects.create(assignment=self.assignment, name="Style")
        RubricCategory.objects.create(assignment=self.assignment, name="Correctness")
        RubricCategory.objects.create(assignment=self.assignment, name="Design")
        self.assertEqual(self.assignment.rubricCategories.count(), 3)


class TestRubricCommentModel(TestCase):
    """Model-level behavior for RubricComment."""

    def setUp(self):
        self.org = OrganizationFactory(name="RubOrg2", shortname="rbo2")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(course=self.course, name="HW1", points=20)
        self.category = RubricCategory.objects.create(assignment=self.assignment, name="General")

    def test_positive_point_delta_for_deduction(self):
        """Positive pointDelta = points deducted."""
        rc = RubricComment.objects.create(category=self.category, text="Missing semicolon", pointDelta=2)
        self.assertEqual(rc.pointDelta, 2)

    def test_negative_point_delta_for_bonus(self):
        """Negative pointDelta = bonus points."""
        rc = RubricComment.objects.create(category=self.category, text="Extra credit", pointDelta=-3)
        self.assertEqual(rc.pointDelta, -3)

    def test_decimal_point_delta(self):
        """Supports 2 decimal places."""
        rc = RubricComment.objects.create(category=self.category, text="Half point", pointDelta=Decimal("0.50"))
        rc.refresh_from_db()
        self.assertEqual(rc.pointDelta, Decimal("0.50"))

    def test_sort_key_default(self):
        rc = RubricComment.objects.create(category=self.category, text="Comment", pointDelta=1)
        self.assertEqual(rc.sortKey, 0)

    def test_course_property(self):
        rc = RubricComment.objects.create(category=self.category, text="Comment", pointDelta=1)
        self.assertEqual(rc.course, self.course)

    def test_cascade_delete_from_category(self):
        rc = RubricComment.objects.create(category=self.category, text="Temp", pointDelta=1)
        rc_id = rc.pk
        self.category.delete()
        self.assertFalse(RubricComment.objects.filter(pk=rc_id).exists())

    def test_template_text_defaults_off(self):
        rc = RubricComment.objects.create(category=self.category, text="Test", pointDelta=1)
        self.assertFalse(rc.templateTextOn)

    def test_instruction_text_blank_by_default(self):
        rc = RubricComment.objects.create(category=self.category, text="Test", pointDelta=1)
        self.assertEqual(rc.instructionText, "")


class TestRubricAPI(APITestCase):
    """API-level rubric tests."""

    def setUp(self):
        setUpBase(self)

    def test_admin_create_rubric_category(self):
        admin = self.course.courseAdmins.first()
        assignment = self.course.assignments.first()
        response = request_as("create", admin, "/rubricCategories/", {
            "assignment": assignment.id,
            "name": "New Category",
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "New Category")

    def test_student_denied_create_rubric_category(self):
        student = self.course.students.first()
        assignment = self.course.assignments.first()
        response = request_as("create", student, "/rubricCategories/", {
            "assignment": assignment.id,
            "name": "Forbidden",
        })
        self.assertIn(response.status_code, [403, 400])

    def test_admin_create_rubric_comment(self):
        admin = self.course.courseAdmins.first()
        category = self.course.assignments.first().rubricCategories.first()
        response = request_as("create", admin, "/rubricComments/", {
            "category": category.id,
            "text": "Good variable names",
            "pointDelta": -1,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["text"], "Good variable names")
        self.assertEqual(float(response.data["pointDelta"]), -1.0)
