# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass
from core.tests.views.personas import Persona

from core.tests.factories import *
from core.models import *

from core.tests.utils import request_as, setUpBase

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class TestPermissions_Course_roster_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)


class TestPermissions_Course_roster(APITestCase):

  def setUp(self):
    # with factory.debug():
    setUpBase(self)

  def test_permission_roster(self):
    student = Persona.STUDENT_OF_SUB(self)
    other_student = User.objects.get(username="student_cos126_0@princeton.edu")
    grader = Persona.GRADER_OF_SUB(self)
    other_grader = User.objects.get(username="grader_cos126_1@princeton.edu")

    supergrader = Persona.SUPERGRADER_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)
    random_admin = Persona.ADMIN_OF_OTHER_COURSE(self)

    endpoint = reverse("course-roster", args=[self.DB['Course'].id])

    #############

    response = request_as('read', other_student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    #############

    response = request_as('read', other_grader, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    #############

    response = request_as('read', random_admin, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    #############

    response = request_as('read', grader, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    #############

    response = request_as('read', supergrader, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    #############

    response = request_as('read', admin, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    #############

    response = request_as('read', student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
