# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from datetime import timedelta

from core.tests.views.personas import Persona

from core.tests.factories import *
from core.models import *

from core.tests.utils import request_as, setUpBase

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

UPLOAD_BODY = {"files": [{"name": "hello.py", "extension": ".py", "path": "", "data": "print('hi')"}]}


class TestPermissions_Assignment_studentUpload(APITestCase):

  def setUp(self):
    # with factory.debug():
    setUpBase(self)

  def _set(self, **kwargs):
    assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
    for key, value in kwargs.items():
      setattr(assignment, key, value)
    assignment.save()
    return assignment

  def test_permission_studentUpload_allowed(self):
    student = Persona.STUDENT_OF_SUB(self)
    other_student = Persona.STUDENT_OF_OTHER_ORG(self)

    endpoint = reverse("assignment-studentUpload", args=[self.DB['Assignment'].id])

    self._set(state='published', allowStudentUpload=True)

    response = request_as('read', student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    response = request_as('read', other_student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_permission_studentUpload_not_allowed(self):
    student = Persona.STUDENT_OF_SUB(self)
    other_student = Persona.STUDENT_OF_OTHER_ORG(self)

    endpoint = reverse("assignment-studentUpload", args=[self.DB['Assignment'].id])

    self._set(state='published', allowStudentUpload=False)

    response = request_as('read', student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    response = request_as('read', other_student, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_studentUpload_denied_unless_published(self):
    """The original exploit: allowStudentUpload alone must never grant upload —
    the assignment has to be published (and, for draft/archived, even visible)."""
    student = Persona.STUDENT_OF_COURSE(self)
    endpoint = reverse("assignment-studentUpload", args=[self.DB['Assignment'].id])

    for state in ('draft', 'visible', 'preview', 'closed', 'archived'):
      self._set(state=state, allowStudentUpload=True)
      response = request_as('read', student, endpoint, {})
      self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                       f"GET studentUpload must 403 in state={state}")
      response = request_as('create', student, endpoint, UPLOAD_BODY)
      self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                       f"POST studentUpload must 403 in state={state}")

  def test_studentUpload_POST_allowed_when_published(self):
    """A real POST body must succeed for a student once published. Guards the
    permission-class/action pairing: AssignmentPermissions must route studentUpload
    POSTs through the student read gate, not the admin-only write branch."""
    student = Persona.STUDENT_OF_COURSE(self)
    endpoint = reverse("assignment-studentUpload", args=[self.DB['Assignment'].id])

    self._set(state='published', allowStudentUpload=True)
    response = request_as('create', student, endpoint, UPLOAD_BODY)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(
        Submission.objects.filter(assignment=self.DB['Assignment'].id, students=student).exists())

  def test_studentUpload_denied_past_late_window(self):
    student = Persona.STUDENT_OF_COURSE(self)
    endpoint = reverse("assignment-studentUpload", args=[self.DB['Assignment'].id])

    # Past the due date with the late window exhausted: derived state is closed.
    self._set(state='published', allowStudentUpload=True, allowLateUploads=True,
              maxLateDays=1, uploadDueDate=timezone.now() - timedelta(days=3))
    response = request_as('create', student, endpoint, UPLOAD_BODY)
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_studentUpload_denied_when_hidden_from_section(self):
    student = Persona.STUDENT_OF_COURSE(self)
    endpoint = reverse("assignment-studentUpload", args=[self.DB['Assignment'].id])

    assignment = self._set(state='published', allowStudentUpload=True)
    section = SectionFactory(course=self.course, name="P99-hidden")
    section.students.add(student)
    assignment.hideFrom.add(section)

    response = request_as('create', student, endpoint, UPLOAD_BODY)
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_studentUpload_admin_allowed_on_draft(self):
    admin = Persona.ADMIN_OF_COURSE(self)
    endpoint = reverse("assignment-studentUpload", args=[self.DB['Assignment'].id])

    self._set(state='draft', allowStudentUpload=False)
    response = request_as('read', admin, endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)
