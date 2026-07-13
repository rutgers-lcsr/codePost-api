# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass
from core.tests.views.personas import Persona
from rest_framework import status
from core.serializers.comment import CommentSerializer

from core.models import *


def _normalize_comment_permissions(permissions, *, allow_student_read: bool):
  read_permissions = permissions.get('read', {})
  for persona in (Persona.STUDENT_OF_SUB, Persona.INACTIVE_STUDENT_OF_SUB):
    if persona in read_permissions:
      if allow_student_read:
        # Keep serializer from existing matrix, only normalize status.
        current = read_permissions[persona]
        serializer = current[1] if len(current) > 1 else None
        read_permissions[persona] = (status.HTTP_200_OK, serializer or CommentSerializer)
      else:
        read_permissions[persona] = (status.HTTP_403_FORBIDDEN,)


class TestPermissions_Comment_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_comment_permissions(self.permissions, allow_student_read=False)
    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)


class TestPermissions_Comment_Finalized(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_comment_permissions(self.permissions, allow_student_read=False)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      submission.isFinalized = True
      submission.save()

    def assertModification(self, detail):
      comment = Comment.objects.get(id=detail)
      submission = comment.file.submission
      self.assertTrue(submission.isFinalized)
      self.assertFalse(submission.assignment.isReleased)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Comment_Released(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_comment_permissions(self.permissions, allow_student_read=False)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.save()

    def assertModification(self, detail):
      comment = Comment.objects.get(id=detail)
      submission = comment.file.submission
      _assignment = submission.assignment
      self.assertFalse(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Comment_FinalizedReleased(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_comment_permissions(self.permissions, allow_student_read=False)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      submission.isFinalized = True
      submission.save()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.save()

    def assertModification(self, detail):
      comment = Comment.objects.get(id=detail)
      submission = comment.file.submission
      _assignment = submission.assignment
      self.assertTrue(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Comment_ReleasedLiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_comment_permissions(self.permissions, allow_student_read=True)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.liveFeedbackMode = True
      assignment.save()

    def assertModification(self, detail):
      comment = Comment.objects.get(id=detail)
      submission = comment.file.submission
      _assignment = submission.assignment
      self.assertFalse(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)
      self.assertTrue(submission.assignment.liveFeedbackMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Comment_UnreleasedLiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_comment_permissions(self.permissions, allow_student_read=True)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = False
      assignment.liveFeedbackMode = True
      assignment.save()

    def assertModification(self, detail):
      comment = Comment.objects.get(id=detail)
      submission = comment.file.submission
      _assignment = submission.assignment
      self.assertFalse(submission.isFinalized)
      self.assertFalse(submission.assignment.isReleased)
      self.assertTrue(submission.assignment.liveFeedbackMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Comment_FinalizedReleasedDontHideGraders(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_comment_permissions(self.permissions, allow_student_read=False)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      submission.isFinalized = True
      submission.save()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.hideGradersFromStudents = False
      assignment.save()

    def assertModification(self, detail):
      submission = Submission.objects.get(id=detail)
      _assignment = submission.assignment
      self.assertTrue(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)
      self.assertFalse(submission.assignment.hideGradersFromStudents)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)
