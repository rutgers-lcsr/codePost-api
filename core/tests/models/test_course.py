# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona


class TestModel_Course(APITestCase):

  def setUp(self):
    setUpBase(self)

  ########################################
  # Fields
  ########################################

  ########################################
  # Unique Together
  ########################################

  def test_create_course_with_same_name_different_org(self):
    user1 = Persona.ADMIN_OF_COURSE(self)
    user2 = Persona.ADMIN_OF_OTHER_ORG(self)

    self.assertEqual(user1.profile.organization, self.course.organization)
    self.assertEqual(user2.profile.organization, self.other_org_course.organization)
    self.assertNotEqual(user1.profile.organization, user2.profile.organization)

    payload1 = {
        "name": "COS333",
        "period": "S2020"
    }

    payload2 = {
        "name": "COS333",
        "period": "S2020"
    }

    self.assertEqual(payload1["name"], payload2["name"])
    self.assertEqual(payload1["period"], payload2["period"])

    response = request_as("create", user1, reverse("course-list"), payload1)
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    response = request_as("create", user2, reverse("course-list"), payload2)
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)

  def test_create_course_with_same_name_same_org(self):
    user1 = Persona.ADMIN_OF_COURSE(self)

    self.assertEqual(user1.profile.organization, self.course.organization)

    payload1 = {
        "name": "COS333",
        "period": "S2020"
    }

    payload2 = {
        "name": "COS333",
        "period": "S2020"
    }

    self.assertEqual(payload1["name"], payload2["name"])
    self.assertEqual(payload1["period"], payload2["period"])

    response = request_as("create", user1, reverse("course-list"), payload1)
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    response = request_as("create", user1, reverse("course-list"), payload2)
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

  def test_create_course_with_same_name_same_org_different_period(self):
    user1 = Persona.ADMIN_OF_COURSE(self)

    self.assertEqual(user1.profile.organization, self.course.organization)

    payload1 = {
        "name": "COS333",
        "period": "S2020"
    }

    payload2 = {
        "name": "COS333",
        "period": "F2020"
    }

    self.assertEqual(payload1["name"], payload2["name"])
    self.assertNotEqual(payload1["period"], payload2["period"])

    response = request_as("create", user1, reverse("course-list"), payload1)
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    response = request_as("create", user1, reverse("course-list"), payload2)
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)

  ########################################
  # Functions
  ########################################
