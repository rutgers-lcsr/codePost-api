# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass
from core.tests.views.personas import Persona

from core.tests.factories import *
from core.models import *

from core.tests.utils import request_as, setUpBase

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class TestPermissions_Assignment_submissions_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)


class TestPermissions_Assignment_submissions(APITestCase):

  def setUp(self):
    # with factory.debug():
    setUpBase(self)

  def test_permission_filter_by_grader(self):
    student = Persona.STUDENT_OF_SUB(self)
    grader = Persona.GRADER_OF_SUB(self)
    other_grader = User.objects.get(username="grader_cos126_1@princeton.edu")

    supergrader = Persona.SUPERGRADER_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)
    random_admin = Persona.ADMIN_OF_OTHER_COURSE(self)

    endpoint = reverse("assignment-submissions", args=[self.DB['Assignment'].id])
    endpoint = endpoint + "?grader={}".format(grader)

    ##############################################################################
    assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
    assignment.state = 'published'
    assignment.liveFeedbackMode = True
    assignment.allowStudentUpload = True
    assignment.save()
    self.assertEqual(assignment.state, 'published')
    self.assertTrue(assignment.liveFeedbackMode)
    self.assertTrue(assignment.allowStudentUpload)
    ##############################################################################

    #############

    response = request_as('read', student, endpoint, {})
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

    subs = list(filter(lambda x: x['grader'] != grader.username, response.data))
    self.assertEqual(len(subs), 0)

    #############

    response = request_as('read', supergrader, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    #############

    response = request_as('read', admin, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

  def test_permission_filter_by_student(self):
    student = Persona.STUDENT_OF_SUB(self)
    other_student = User.objects.get(username="student_cos126_0@princeton.edu")
    grader = Persona.GRADER_OF_SUB(self)
    other_grader = User.objects.get(username="grader_cos126_1@princeton.edu")

    supergrader = Persona.SUPERGRADER_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)
    random_admin = Persona.ADMIN_OF_OTHER_COURSE(self)

    endpoint = reverse("assignment-submissions", args=[self.DB['Assignment'].id])
    endpoint = endpoint + "?student={}".format(student)

    ##############################################################################
    assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
    self.assertNotIn(assignment.state, ('published', 'closed'))
    self.assertFalse(assignment.liveFeedbackMode)
    self.assertFalse(assignment.allowStudentUpload)
    ##############################################################################

    #############

    response = request_as('read', other_student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    #############

    response = request_as('read', other_grader, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

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

    assignment.state = 'published'
    assignment.liveFeedbackMode = True
    assignment.allowStudentUpload = True
    assignment.save()
    self.assertEqual(assignment.state, 'published')
    self.assertTrue(assignment.liveFeedbackMode)
    self.assertTrue(assignment.allowStudentUpload)

    response = request_as('read', student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertLessEqual(len(response.data), 1)

  def test_permission_filter_none(self):
    student = Persona.STUDENT_OF_SUB(self)
    other_student = User.objects.get(username="student_cos126_0@princeton.edu")
    grader = Persona.GRADER_OF_SUB(self)
    other_grader = User.objects.get(username="grader_cos126_1@princeton.edu")

    supergrader = Persona.SUPERGRADER_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)
    random_admin = Persona.ADMIN_OF_OTHER_COURSE(self)

    endpoint = reverse("assignment-submissions", args=[self.DB['Assignment'].id])

    ##############################################################################
    assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
    assignment.state = 'published'
    assignment.liveFeedbackMode = True
    assignment.allowStudentUpload = True
    assignment.save()
    self.assertEqual(assignment.state, 'published')
    self.assertTrue(assignment.liveFeedbackMode)
    self.assertTrue(assignment.allowStudentUpload)
    ##############################################################################

    #############

    response = request_as('read', student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
