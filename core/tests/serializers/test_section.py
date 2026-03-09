# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona
import unittest


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
