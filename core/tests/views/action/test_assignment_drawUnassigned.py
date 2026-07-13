# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass
from core.tests.views.personas import Persona

from core.tests.factories import *
from core.models import *

from core.tests.utils import request_as, setUpBase

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class TestPermissions_Assignment_drawUnassigned_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    def modifier(self):
      assignment = Assignment.objects.filter(course=self.course).first()
      submission = SubmissionFactory(assignment=assignment)
      submission.isFinalized = False
      submission.grader = None
      submission.students.set([self.course.students.last()])
      submission.save()

    def assertModification(self, detail):
      assignment = Assignment.objects.get(id=detail)

      unclaimed_submissions = assignment.submissions.filter(grader=None)

      self.assertGreater(unclaimed_submissions.count(), 0)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Assignment_drawUnassigned(APITestCase):

  def setUp(self):
    # with factory.debug():
    setUpBase(self)

  def test_permission_rubric_released(self):
    student = Persona.STUDENT_OF_SUB(self)
    grader = Persona.GRADER_OF_SUB(self)
    other_grader = User.objects.get(username="grader_cos126_1@princeton.edu")

    supergrader = Persona.SUPERGRADER_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)
    random_admin = Persona.ADMIN_OF_OTHER_COURSE(self)

    endpoint = reverse("assignment-drawUnassigned", args=[self.DB['Assignment'].id])

    ##############################################################################
    assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
    assignment.isReleased = True
    assignment.liveFeedbackMode = True
    assignment.allowStudentUpload = True
    assignment.save()
    self.assertTrue(assignment.isReleased)
    self.assertTrue(assignment.liveFeedbackMode)
    self.assertTrue(assignment.allowStudentUpload)
    ##############################################################################

    #############

    response = request_as('read', student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    #############

    response = request_as('read', other_grader, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    #############

    response = request_as('read', random_admin, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    #############

    response = request_as('read', grader, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    #############

    response = request_as('read', supergrader, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    #############

    # Admin that's not a grader
    response = request_as('read', admin, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
