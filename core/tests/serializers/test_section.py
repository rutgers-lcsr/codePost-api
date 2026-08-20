# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *


class TestSerializer_SectionSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass

    def test_add_leaders_and_students(self):
        """Section serializer validates that leaders are graders and students are enrolled."""
        admin = self.course.courseAdmins.first()
        grader = self.course.graders.first()
        student = self.course.students.first()
        response = request_as("create", admin, "/sections/", {
            "course": self.course.id,
            "name": "NewSection",
            "leaders": [grader.email],
            "students": [student.email],
        })
        self.assertEqual(response.status_code, 201)
        self.assertIn(grader.email, response.data["leaders"])
        self.assertIn(student.email, response.data["students"])

    def test_add_non_grader_as_leader_fails(self):
        """Trying to add a student as a section leader should fail."""
        admin = self.course.courseAdmins.first()
        student = self.course.students.first()
        response = request_as("create", admin, "/sections/", {
            "course": self.course.id,
            "name": "BadSection",
            "leaders": [student.email],
            "students": [],
        })
        self.assertIn(response.status_code, [400, 403])

    def test_patch_leaders_only_succeeds(self):
        """A PATCH carrying only leaders must not crash (regression: the student-dedup loop
        used to read newData['students'] unconditionally) and must not touch students."""
        admin = self.course.courseAdmins.first()
        grader = self.course.graders.first()
        section = self.course.sections.first()
        students_before = sorted(s.email for s in section.students.all())
        response = request_as("update", admin, f"/sections/{section.id}/",
                              {"leaders": [grader.email]})
        self.assertEqual(response.status_code, 200)
        section.refresh_from_db()
        self.assertEqual([leader.email for leader in section.leaders.all()], [grader.email])
        self.assertEqual(sorted(s.email for s in section.students.all()), students_before)

    def test_patch_leaders_only_rejects_non_grader(self):
        admin = self.course.courseAdmins.first()
        student = self.course.students.first()
        section = self.course.sections.first()
        response = request_as("update", admin, f"/sections/{section.id}/",
                              {"leaders": [student.email]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a member", str(response.data))

    def test_patch_name_only_succeeds(self):
        admin = self.course.courseAdmins.first()
        section = self.course.sections.first()
        response = request_as("update", admin, f"/sections/{section.id}/",
                              {"name": "Renamed"})
        self.assertEqual(response.status_code, 200)
        section.refresh_from_db()
        self.assertEqual(section.name, "Renamed")

    def test_patch_students_only_moves_student_between_sections(self):
        """The one-section-per-student dedup still runs on a students-carrying PATCH."""
        from core.models import Section
        admin = self.course.courseAdmins.first()
        student = self.course.students.first()
        first = self.course.sections.first()
        first.students.add(student)
        second = Section.objects.create(name="Second", course=self.course)
        response = request_as("update", admin, f"/sections/{second.id}/",
                              {"students": [student.email]})
        self.assertEqual(response.status_code, 200)
        self.assertIn(student, second.students.all())
        self.assertNotIn(student, first.students.all())

    def test_leaders_patch_requires_admin(self):
        """Section writes are admin-only — the assign-graders matrix is an admin surface."""
        grader = self.course.graders.first()
        section = self.course.sections.first()
        response = request_as("update", grader, f"/sections/{section.id}/",
                              {"leaders": [grader.email]})
        self.assertEqual(response.status_code, 403)
