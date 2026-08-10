# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.personas import Persona

from core.tests.factories import *
from core.models import *

from core.tests.utils import request_as, setUpBase

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class TestPermissions_Assignment_beforeStudentUpload(APITestCase):

  def setUp(self):
    setUpBase(self)

  def _set(self, **kwargs):
    assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
    for key, value in kwargs.items():
      setattr(assignment, key, value)
    assignment.save()
    return assignment

  def test_beforeStudentUpload_allowed_when_published(self):
    student = Persona.STUDENT_OF_COURSE(self)
    endpoint = reverse("assignment-beforeStudentUpload", args=[self.DB['Assignment'].id])

    self._set(state='published', allowStudentUpload=True)
    response = request_as('read', student, endpoint)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data['daysLate'], 0)

  def test_beforeStudentUpload_denied_unless_published(self):
    """Late-day math must not leak for assignments students cannot submit to."""
    student = Persona.STUDENT_OF_COURSE(self)
    endpoint = reverse("assignment-beforeStudentUpload", args=[self.DB['Assignment'].id])

    for state in ('draft', 'visible', 'preview', 'closed', 'archived'):
      self._set(state=state, allowStudentUpload=True)
      response = request_as('read', student, endpoint)
      self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                       f"beforeStudentUpload must 403 in state={state}")

  def test_beforeStudentUpload_denied_when_upload_disabled(self):
    student = Persona.STUDENT_OF_COURSE(self)
    endpoint = reverse("assignment-beforeStudentUpload", args=[self.DB['Assignment'].id])

    self._set(state='published', allowStudentUpload=False)
    response = request_as('read', student, endpoint)
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_beforeStudentUpload_denied_when_hidden_from_section(self):
    student = Persona.STUDENT_OF_COURSE(self)
    endpoint = reverse("assignment-beforeStudentUpload", args=[self.DB['Assignment'].id])

    assignment = self._set(state='published', allowStudentUpload=True)
    section = SectionFactory(course=self.course, name="P99-hidden")
    section.students.add(student)
    assignment.hideFrom.add(section)

    response = request_as('read', student, endpoint)
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
