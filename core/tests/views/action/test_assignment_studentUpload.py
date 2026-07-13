# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.personas import Persona

from core.tests.factories import *
from core.models import *

from core.tests.utils import request_as, setUpBase

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class TestPermissions_Assignment_studentUpload(APITestCase):

  def setUp(self):
    # with factory.debug():
    setUpBase(self)

  def test_permission_studentUpload_allowed(self):
    student = Persona.STUDENT_OF_SUB(self)
    other_student = Persona.STUDENT_OF_OTHER_ORG(self)

    endpoint = reverse("assignment-studentUpload", args=[self.DB['Assignment'].id])

    ##############################################################################
    assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
    assignment.allowStudentUpload = True
    assignment.save()
    self.assertTrue(assignment.allowStudentUpload)
    ##############################################################################

    #############

    response = request_as('read', student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    response = request_as('read', other_student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
  def test_permission_studentUpload_not_allowed(self):
    student = Persona.STUDENT_OF_SUB(self)
    other_student = Persona.STUDENT_OF_OTHER_ORG(self)

    endpoint = reverse("assignment-studentUpload", args=[self.DB['Assignment'].id])

    ##############################################################################
    assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
    assignment.allowStudentUpload = False
    assignment.save()
    self.assertFalse(assignment.allowStudentUpload)
    ##############################################################################

    #############

    response = request_as('read', student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    response = request_as('read', other_student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

