# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass
from core.tests.views.personas import Persona
from rest_framework import status
from core.serializers.file import FileSerializer, SubmissionFileSerializer

from core.models import *
from core.tests.views.results.file import PERMISSIONS


def _submission_for_file(file_obj: File) -> Submission:
  if hasattr(file_obj, 'submissionfile'):
    return file_obj.submissionfile.submission
  return SubmissionFile.objects.get(id=file_obj.id).submission


def _normalize_permissions(permissions):
  create_permissions = permissions.get('create', {})
  for persona, expected in list(create_permissions.items()):
    if expected and expected[0] == status.HTTP_201_CREATED:
      create_permissions[persona] = (status.HTTP_201_CREATED, SubmissionFileSerializer)

  read_permissions = permissions.get('read', {})
  if Persona.STUDENT_OF_SUB in read_permissions:
    read_permissions[Persona.STUDENT_OF_SUB] = (status.HTTP_200_OK, FileSerializer)
  if Persona.INACTIVE_STUDENT_OF_SUB in read_permissions:
    read_permissions[Persona.INACTIVE_STUDENT_OF_SUB] = (status.HTTP_200_OK, FileSerializer)


class TestPermissions_File_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_permissions(self.permissions)

    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)


class TestPermissions_File_Finalized(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_permissions(self.permissions)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      submission.isFinalized = True
      submission.save()

    def assertModification(self, detail):
      file = File.objects.get(id=detail)
      submission = _submission_for_file(file)
      self.assertTrue(submission.isFinalized)
      self.assertNotIn(submission.assignment.state, ('published', 'closed'))

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_File_Released(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_permissions(self.permissions)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.state = 'published'
      assignment.save()

    def assertModification(self, detail):
      file = File.objects.get(id=detail)
      submission = _submission_for_file(file)
      self.assertFalse(submission.isFinalized)
      self.assertEqual(submission.assignment.state, 'published')

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_File_FinalizedReleased(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_permissions(self.permissions)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      submission.isFinalized = True
      submission.save()
      assignment = submission.assignment
      assignment.state = 'published'
      assignment.save()

    def assertModification(self, detail):
      file = File.objects.get(id=detail)
      submission = _submission_for_file(file)
      _assignment = submission.assignment
      self.assertTrue(submission.isFinalized)
      self.assertEqual(submission.assignment.state, 'published')

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_File_ReleasedLiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_permissions(self.permissions)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.state = 'published'
      assignment.liveFeedbackMode = True
      assignment.save()

    def assertModification(self, detail):
      file = File.objects.get(id=detail)
      submission = _submission_for_file(file)
      self.assertFalse(submission.isFinalized)
      self.assertEqual(submission.assignment.state, 'published')
      self.assertTrue(submission.assignment.liveFeedbackMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_File_UnreleasedLiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_permissions(self.permissions)

    # Extra check on our manual results
    self.assertDictEqual(PERMISSIONS["PERMISSIONS_UNRELEASEDLIVEFEEDBACK"],
                         PERMISSIONS["PERMISSIONS_RELEASEDLIVEFEEDBACK"])
    self.assertDictEqual(PERMISSIONS["PERMISSIONS_UNRELEASEDLIVEFEEDBACK"], PERMISSIONS["PERMISSIONS_RELEASED"])

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.state = 'preview'
      assignment.liveFeedbackMode = True
      assignment.save()

    def assertModification(self, detail):
      file = File.objects.get(id=detail)
      submission = _submission_for_file(file)
      self.assertFalse(submission.isFinalized)
      self.assertNotIn(submission.assignment.state, ('published', 'closed'))
      self.assertTrue(submission.assignment.liveFeedbackMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)
