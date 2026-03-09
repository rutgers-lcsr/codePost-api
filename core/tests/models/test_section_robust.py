# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Robust tests for Section model.

Covers:
- Unique together constraint (name + course)
- Same name in different courses is allowed
- Section string representation
- Leader and student ManyToMany relationships
- Deletion cascade behavior
"""
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Section, Course
from core.tests.utils import request_as, setUpBase, setUpClient, setUpCourse, setUpSection
from core.tests.factories import (
    CourseFactory, OrganizationFactory,
)
from core.tests.views.personas import Persona


class TestSectionModelConstraints(TestCase):
    """Model-level constraint + behavior tests."""

    def setUp(self):
        setUpClient(self)

    def test_unique_name_per_course(self):
        """Two sections in the same course cannot have the same name."""
        course = setUpCourse(self)
        Section.objects.create(name="Lab A", course=course)
        with self.assertRaises(IntegrityError):
            Section.objects.create(name="Lab A", course=course)

    def test_same_name_different_course(self):
        """Sections with the same name in different courses are allowed."""
        course1 = setUpCourse(self)
        org = course1.organization
        course2 = Course.objects.create(name="CS202", period="F2025", organization=org)
        s1 = Section.objects.create(name="Lab A", course=course1)
        s2 = Section.objects.create(name="Lab A", course=course2)
        self.assertNotEqual(s1.id, s2.id)

    def test_str_includes_name_and_course(self):
        """Section.__str__ includes section name and course."""
        section = setUpSection(self)
        s = str(section)
        self.assertIn(section.name, s)
        self.assertIn(str(section.course), s)

    def test_section_cascade_deleted_with_course(self):
        """Deleting a course cascades to its sections."""
        course = setUpCourse(self)
        sec = Section.objects.create(name="Doomed Section", course=course)
        sec_id = sec.id
        self.assertTrue(Section.objects.filter(id=sec_id).exists())
        course.delete()
        self.assertFalse(Section.objects.filter(id=sec_id).exists())

    def test_add_leaders_and_students_to_section(self):
        """Leaders and students can be added to a section's ManyToMany fields."""
        section = setUpSection(self)
        from django.contrib.auth.models import User
        leader = User.objects.create(username="leader@test.edu", email="leader@test.edu")
        student = User.objects.create(username="student@test.edu", email="student@test.edu")
        section.leaders.add(leader)
        section.students.add(student)
        self.assertIn(leader, section.leaders.all())
        self.assertIn(student, section.students.all())
        self.assertEqual(section.leaders.count(), 1)
        self.assertEqual(section.students.count(), 1)

    def test_ordering_is_by_name(self):
        """Sections are ordered alphabetically by name."""
        course = setUpCourse(self)
        Section.objects.create(name="Z-Section", course=course)
        Section.objects.create(name="A-Section", course=course)
        Section.objects.create(name="M-Section", course=course)
        names = list(Section.objects.filter(course=course).values_list('name', flat=True))
        self.assertEqual(names, sorted(names))


class TestSectionAPI(APITestCase):
    """API-level section tests."""

    def setUp(self):
        setUpBase(self)

    def test_admin_can_create_section(self):
        """Course admin can create a section."""
        user = Persona.ADMIN_OF_COURSE(self)
        grader = Persona.GRADER_OF_COURSE(self)
        student = Persona.STUDENT_OF_COURSE(self)
        payload = {
            "course": self.course.id,
            "name": "New Section",
            "leaders": [grader.email],
            "students": [student.email],
        }
        response = request_as("create", user, reverse("section-list"), payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "New Section")

    def test_student_cannot_create_section(self):
        """Students should not be able to create sections."""
        user = Persona.STUDENT_OF_COURSE(self)
        grader = Persona.GRADER_OF_COURSE(self)
        payload = {
            "course": self.course.id,
            "name": "Forbidden Section",
            "leaders": [grader.email],
            "students": [user.email],
        }
        response = request_as("create", user, reverse("section-list"), payload)
        # Students get 400 (validation) or 403 (permission) — both are rejection
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

    def test_admin_can_update_section(self):
        """Admin can rename a section."""
        user = Persona.ADMIN_OF_COURSE(self)
        section = self.DB["Section"]
        payload = {
            "name": "Renamed",
            "leaders": [],
            "students": [],
        }
        response = request_as("update", user,
                              reverse("section-detail", args=[section.id]),
                              payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Renamed")
