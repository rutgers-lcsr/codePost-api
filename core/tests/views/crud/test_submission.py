# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass
from core.tests.views.personas import Persona
from rest_framework import status
from core.serializers.submission import SubmissionSerializer

from core.tests.views.results.submission import PERMISSIONS

from core.models import *


def _normalize_submission_permissions(permissions, model_name):
  read_permissions = permissions.get('read', {})
  for persona in (Persona.STUDENT_OF_SUB, Persona.INACTIVE_STUDENT_OF_SUB):
    if persona in read_permissions:
      read_permissions[persona] = (status.HTTP_200_OK, SubmissionSerializer)


class TestPermissions_Submission_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_submission_permissions(self.permissions, self.model)

    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)


class TestPermissions_Submission_Finalized(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_submission_permissions(self.permissions, self.model)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      submission.isFinalized = True
      submission.save()

    def assertModification(self, detail):
      submission = Submission.objects.get(id=detail)
      self.assertTrue(submission.isFinalized)
      self.assertFalse(submission.assignment.isReleased)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Submission_Released(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_submission_permissions(self.permissions, self.model)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.save()

    def assertModification(self, detail):
      submission = Submission.objects.get(id=detail)
      _assignment = submission.assignment
      self.assertFalse(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Submission_FinalizedReleased(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_submission_permissions(self.permissions, self.model)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      submission.isFinalized = True
      submission.save()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.save()

    def assertModification(self, detail):
      submission = Submission.objects.get(id=detail)
      _assignment = submission.assignment
      self.assertTrue(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Submission_ReleasedLiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_submission_permissions(self.permissions, self.model)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.liveFeedbackMode = True
      assignment.save()

    def assertModification(self, detail):
      submission = Submission.objects.get(id=detail)
      _assignment = submission.assignment
      self.assertFalse(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)
      self.assertTrue(submission.assignment.liveFeedbackMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Submission_UnreleasedLiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_submission_permissions(self.permissions, self.model)

    # Extra check on our manual results
    self.assertDictEqual(PERMISSIONS["PERMISSIONS_UNRELEASEDLIVEFEEDBACK"],
                         PERMISSIONS["PERMISSIONS_RELEASEDLIVEFEEDBACK"])

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = False
      assignment.liveFeedbackMode = True
      assignment.save()

    def assertModification(self, detail):
      submission = Submission.objects.get(id=detail)
      _assignment = submission.assignment
      self.assertFalse(submission.isFinalized)
      self.assertFalse(submission.assignment.isReleased)
      self.assertTrue(submission.assignment.liveFeedbackMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Submission_FinalizedReleasedAnonymous(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_submission_permissions(self.permissions, self.model)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      submission.isFinalized = True
      submission.save()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.anonymousGrading = True
      assignment.save()

    def assertModification(self, detail):
      submission = Submission.objects.get(id=detail)
      _assignment = submission.assignment
      self.assertTrue(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)
      self.assertTrue(submission.assignment.anonymousGrading)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Submission_FinalizedReleasedHideGrades(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_submission_permissions(self.permissions, self.model)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      submission.isFinalized = True
      submission.save()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.hideGrades = True
      assignment.save()

    def assertModification(self, detail):
      submission = Submission.objects.get(id=detail)
      _assignment = submission.assignment
      self.assertTrue(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)
      self.assertTrue(submission.assignment.hideGrades)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)
