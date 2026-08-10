# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Endpoint coverage for the partner-link flow. The invitee gate mirrors
upload_submission: the target assignment must be published/open and not hidden from the
invitee's section — failures are an opaque 406, and the invitee must not be attached."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Assignment, Submission
from core.permissions.tokens import submission_token_generator
from core.tests.factories import *
from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona


class TestPartnerLinks(APITestCase):

  def setUp(self):
    setUpBase(self)
    self.assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
    self.assignment.state = 'published'
    self.assignment.allowStudentUpload = True
    self.assignment.allowStudentUploadWithPartners = True
    self.assignment.save()
    self.submission = self.DB['Submission']
    self.owner = Persona.STUDENT_OF_SUB(self)
    # A course student not on any submission for this assignment.
    self.invitee = UserFactory(username='invitee', email='invitee@x.com')
    self.course.students.add(self.invitee)
    self.token = submission_token_generator.make_token(self.submission)

  def _validate(self, user, token=None):
    endpoint = reverse("submission-validatePartnerLink", args=[self.submission.id])
    return request_as('read', user, f"{endpoint}?token={token or self.token}")

  def test_valid_token_published_adds_invitee(self):
    response = self._validate(self.invitee)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertIn(self.invitee, self.submission.students.all())

  def test_denied_unless_published(self):
    for state in ('draft', 'visible', 'preview', 'closed', 'archived'):
      self.assignment.state = state
      self.assignment.save()
      response = self._validate(self.invitee)
      self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE,
                       f"validatePartnerLink must 406 in state={state}")
      self.assertNotIn(self.invitee, self.submission.students.all(),
                       f"invitee must not be attached in state={state}")

  def test_denied_when_hidden_from_invitee_section(self):
    section = SectionFactory(course=self.course, name="P99-hidden")
    section.students.add(self.invitee)
    self.assignment.hideFrom.add(section)

    response = self._validate(self.invitee)
    self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)
    self.assertNotIn(self.invitee, self.submission.students.all())

  def test_denied_when_partners_disabled(self):
    self.assignment.allowStudentUploadWithPartners = False
    self.assignment.save()
    response = self._validate(self.invitee)
    self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

  def test_denied_with_garbage_token(self):
    response = self._validate(self.invitee, token='garbage')
    self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)
    self.assertNotIn(self.invitee, self.submission.students.all())

  def test_denied_for_non_student(self):
    grader = Persona.GRADER_OF_COURSE(self)
    response = self._validate(grader)
    self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

  def test_generatePartnerLink_denied_on_hidden_assignment(self):
    # The owner loses partner management once the assignment is no longer submittable.
    self.assignment.state = 'draft'
    self.assignment.save()
    endpoint = reverse("submission-generatePartnerLink", args=[self.submission.id])
    response = request_as('read', self.owner, endpoint)
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_generatePartnerLink_allowed_when_published(self):
    endpoint = reverse("submission-generatePartnerLink", args=[self.submission.id])
    response = request_as('read', self.owner, endpoint)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertIn('token', response.data)
