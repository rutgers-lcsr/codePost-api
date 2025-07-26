from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona


class TestModel_Assignment(APITestCase):

    def setUp(self):
        setUpBase(self)

    ########################################
    # Fields
    ########################################

    def test_create_assignment_with_negative_points(self):
        user = Persona.ADMIN_OF_COURSE(self)
        self.assertEqual(user.courseAdmin_courses.first(), self.course)

        payload = {
            "course": self.course.id,
            "name": "New Assignment",
            "points": -10,
            "isReleased": False,
        }

        self.assertTrue(payload['points'] < 0)

        response = request_as("create", user, reverse("assignment-list"), payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    ########################################
    # Unique Together
    ########################################

    def test_create_assignment_with_same_name_different_course(self):
        user1 = Persona.ADMIN_OF_COURSE(self)
        user2 = Persona.ADMIN_OF_OTHER_COURSE(self)

        self.assertEqual(user1.courseAdmin_courses.first(), self.course)
        self.assertEqual(user2.courseAdmin_courses.first(), self.other_course)

        payload1 = {
            "course": self.course.id,
            "name": "New Assignment",
            "points": 20,
            "isReleased": False,
        }

        payload2 = {
            "course": self.other_course.id,
            "name": "New Assignment",
            "points": 20,
            "isReleased": False,
        }

        self.assertNotEqual(payload1["course"], payload2["course"])
        self.assertEqual(payload1["name"], payload2["name"])

        response = request_as("create", user1, reverse("assignment-list"), payload1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = request_as("create", user2, reverse("assignment-list"), payload2)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_assignment_with_same_name_same_course(self):
        user1 = Persona.ADMIN_OF_COURSE(self)

        self.assertEqual(user1.courseAdmin_courses.first(), self.course)

        payload1 = {
            "course": self.course.id,
            "name": "New Assignment",
            "points": 20,
            "isReleased": False,
        }

        payload2 = {
            "course": self.course.id,
            "name": "New Assignment",
            "points": 25,
            "isReleased": True,
        }

        self.assertEqual(payload1["course"], payload2["course"])
        self.assertEqual(payload1["name"], payload2["name"])

        response = request_as("create", user1, reverse("assignment-list"), payload1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = request_as("create", user1, reverse("assignment-list"), payload2)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    ########################################
    # Functions
    ########################################

    def test_calculate_average_and_median(self):
        # self.fail('not implemented yet')
        pass
