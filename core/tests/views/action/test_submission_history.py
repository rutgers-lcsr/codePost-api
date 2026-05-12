# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.tests.views.personas import Persona

from core.tests.factories import *
from core.models import *

from core.tests.utils import request_as, setUpBase

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class TestPermissions_Submission_history(APITestCase):

  def setUp(self):
    # with factory.debug():
    setUpBase(self)

  def test_permission_filter_by_student(self):
    student = Persona.STUDENT_OF_SUB(self)
    other_student = User.objects.get(username="student_cos126_0@princeton.edu")
    grader = Persona.GRADER_OF_SUB(self)
    other_grader = User.objects.get(username="grader_cos126_1@princeton.edu")

    supergrader = Persona.SUPERGRADER_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)
    random_admin = Persona.ADMIN_OF_OTHER_COURSE(self)

    endpoint = reverse("submission-history", args=[self.DB['Submission'].id])
    endpoint = endpoint + "?student={}".format(student)

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
    self.assertEqual(response.status_code, status.HTTP_200_OK)

  def test_permission_filter_none(self):
    student = Persona.STUDENT_OF_SUB(self)
    other_student = Persona.STUDENT_OF_OTHER_ORG(self)
    grader = Persona.GRADER_OF_SUB(self)
    other_grader = User.objects.get(username="grader_cos126_1@princeton.edu")

    supergrader = Persona.SUPERGRADER_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)
    random_admin = Persona.ADMIN_OF_OTHER_COURSE(self)

    endpoint = reverse("submission-history", args=[self.DB['Submission'].id])

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
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    #############

    response = request_as('read', supergrader, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    #############

    response = request_as('read', admin, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    #############

    response = request_as('read', student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
