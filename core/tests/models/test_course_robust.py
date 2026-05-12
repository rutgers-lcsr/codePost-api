# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Robust tests for Course model.

Covers:
- unique_together (name, period, organization)
- AI configuration fields
- Archiving behavior
- Roster M2M relationships
- Course properties
- String representation
"""
from django.test import TestCase
from django.db import IntegrityError

from core.models import Course
from core.tests.factories import (
    OrganizationFactory, GraderFactory, StudentFactory,
)


class TestCourseModelConstraints(TestCase):
    """unique_together and meta behavior."""

    def test_unique_together_name_period_org(self):
        """Two courses with same name+period+org should fail."""
        org = OrganizationFactory(name="TestOrg1", shortname="to1")
        Course.objects.create(name="CS101", period="F2020", organization=org)
        with self.assertRaises(IntegrityError):
            Course.objects.create(name="CS101", period="F2020", organization=org)

    def test_same_name_different_period_ok(self):
        """Same name, different period is fine."""
        org = OrganizationFactory(name="TestOrg2", shortname="to2")
        c1 = Course.objects.create(name="CS101", period="F2020", organization=org)
        c2 = Course.objects.create(name="CS101", period="S2021", organization=org)
        self.assertNotEqual(c1.pk, c2.pk)

    def test_same_name_different_org_ok(self):
        """Same name+period, different org is fine."""
        org1 = OrganizationFactory(name="TestOrg3", shortname="to3")
        org2 = OrganizationFactory(name="TestOrg4", shortname="to4")
        c1 = Course.objects.create(name="CS101", period="F2020", organization=org1)
        c2 = Course.objects.create(name="CS101", period="F2020", organization=org2)
        self.assertNotEqual(c1.pk, c2.pk)

    def test_ordering_by_name_then_period(self):
        """Meta ordering is ('name', 'period')."""
        org = OrganizationFactory(name="TestOrg5", shortname="to5")
        Course.objects.create(name="CS201", period="F2020", organization=org)
        Course.objects.create(name="CS101", period="S2020", organization=org)
        Course.objects.create(name="CS101", period="F2020", organization=org)
        courses = list(Course.objects.filter(organization=org))
        names = [(c.name, c.period) for c in courses]
        self.assertEqual(names, [("CS101", "F2020"), ("CS101", "S2020"), ("CS201", "F2020")])

    def test_str(self):
        org = OrganizationFactory(name="TestOrg6", shortname="to6")
        c = Course.objects.create(name="CS101", period="F2020", organization=org)
        self.assertIn("CS101", str(c))
        self.assertIn("F2020", str(c))


class TestCourseDefaults(TestCase):
    """Default field values."""

    def test_archived_defaults_false(self):
        org = OrganizationFactory(name="DefOrg1", shortname="do1")
        c = Course.objects.create(name="CS101", period="F2020", organization=org)
        self.assertFalse(c.archived)

    def test_timezone_defaults_eastern(self):
        org = OrganizationFactory(name="DefOrg2", shortname="do2")
        c = Course.objects.create(name="CS101", period="F2020", organization=org)
        self.assertEqual(c.timezone, "US/Eastern")

    def test_min_comments_defaults_zero(self):
        org = OrganizationFactory(name="DefOrg3", shortname="do3")
        c = Course.objects.create(name="CS101", period="F2020", organization=org)
        self.assertEqual(c.minComments, 0)


class TestCourseRoster(TestCase):
    """M2M roster relationships."""

    def test_add_students(self):
        org = OrganizationFactory(name="RosterOrg1", shortname="ro1")
        c = Course.objects.create(name="CS101", period="F2020", organization=org)
        s1 = StudentFactory(organization=org, course="cs101", count=10)
        s2 = StudentFactory(organization=org, course="cs101", count=11)
        c.students.add(s1, s2)
        self.assertEqual(c.students.count(), 2)
        self.assertIn(s1, c.students.all())

    def test_add_graders_and_supergraders(self):
        org = OrganizationFactory(name="RosterOrg2", shortname="ro2")
        c = Course.objects.create(name="CS101", period="F2020", organization=org)
        g = GraderFactory(organization=org, course="cs101", count=10)
        c.graders.add(g)
        c.superGraders.add(g)
        self.assertIn(g, c.graders.all())
        self.assertIn(g, c.superGraders.all())

    def test_inactive_students(self):
        org = OrganizationFactory(name="RosterOrg3", shortname="ro3")
        c = Course.objects.create(name="CS101", period="F2020", organization=org)
        s = StudentFactory(organization=org, course="cs101", count=12)
        c.students.add(s)
        c.inactive_students.add(s)
        self.assertIn(s, c.students.all())
        self.assertIn(s, c.inactive_students.all())


class TestCourseAIConfig(TestCase):
    """AI configuration fields."""

    def test_ai_defaults(self):
        org = OrganizationFactory(name="AIOrg1", shortname="aio1")
        c = Course.objects.create(name="CS101", period="F2020", organization=org)
        self.assertFalse(c.ai_disabled)
        self.assertFalse(c.ai_comments_disabled)
        self.assertFalse(c.ai_use_own_settings)
        self.assertIsNone(c.ai_provider)
        self.assertIsNone(c.ai_model)

    def test_ai_provider_choices(self):
        org = OrganizationFactory(name="AIOrg2", shortname="aio2")
        c = Course.objects.create(name="CS101", period="F2020", organization=org, ai_provider="openai")
        c.refresh_from_db()
        self.assertEqual(c.ai_provider, "openai")


class TestCourseCascade(TestCase):
    """Cascade delete behavior."""

    def test_delete_org_cascades_courses(self):
        org = OrganizationFactory(name="CascOrg1", shortname="co1")
        Course.objects.create(name="CS101", period="F2020", organization=org)
        Course.objects.create(name="CS201", period="F2020", organization=org)
        org_id = org.pk
        self.assertEqual(Course.objects.filter(organization_id=org_id).count(), 2)
        org.delete()
        self.assertEqual(Course.objects.filter(organization_id=org_id).count(), 0)

    def test_course_property_returns_self(self):
        """course.course should return self (defined as a property)."""
        org = OrganizationFactory(name="CascOrg2", shortname="co2")
        c = Course.objects.create(name="CS101", period="F2020", organization=org)
        self.assertEqual(c.course, c)
