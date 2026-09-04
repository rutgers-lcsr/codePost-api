# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass
from core.tests.views.personas import Persona
from rest_framework import status
from core.serializers.rubricComment import RubricCommentSerializer


from core.models import *


def _normalize_rubric_comment_permissions(permissions, *, allow_student_read: bool):
  read_permissions = permissions.get('read', {})
  for persona in (Persona.STUDENT_OF_COURSE, Persona.STUDENT_OF_OTHER_SUB, Persona.STUDENT_OF_SUB):
    if persona in read_permissions:
      if allow_student_read:
        current = read_permissions[persona]
        serializer = current[1] if len(current) > 1 else None
        read_permissions[persona] = (status.HTTP_200_OK, serializer or RubricCommentSerializer)
      else:
        read_permissions[persona] = (status.HTTP_403_FORBIDDEN,)


class TestPermissions_RubricComment_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_rubric_comment_permissions(self.permissions, allow_student_read=False)
    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)


class TestPermissions_RubricComment_Released(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_rubric_comment_permissions(self.permissions, allow_student_read=False)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.state = 'published'
      assignment.save()

    def assertModification(self, detail):
      rubricComment = RubricComment.objects.get(id=detail)
      assignment = rubricComment.category.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricComment.category.assignment)
      self.assertEqual(assignment.state, 'published')
      self.assertFalse(assignment.collaborativeRubricMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_RubricComment_CollaborativeRubric(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_rubric_comment_permissions(self.permissions, allow_student_read=False)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.collaborativeRubricMode = True
      assignment.save()

    def assertModification(self, detail):
      rubricComment = RubricComment.objects.get(id=detail)
      assignment = rubricComment.category.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricComment.category.assignment)
      self.assertNotIn(assignment.state, ('published', 'closed'))
      self.assertTrue(assignment.collaborativeRubricMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_RubricComment_ReleasedCollaborativeRubric(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_rubric_comment_permissions(self.permissions, allow_student_read=False)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.state = 'published'
      assignment.collaborativeRubricMode = True
      assignment.save()

    def assertModification(self, detail):
      rubricComment = RubricComment.objects.get(id=detail)
      assignment = rubricComment.category.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricComment.category.assignment)
      self.assertEqual(assignment.state, 'published')
      self.assertTrue(assignment.collaborativeRubricMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_RubricComment_LiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    _normalize_rubric_comment_permissions(self.permissions, allow_student_read=True)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.feedbackStatus = 'live'
      assignment.save()

    def assertModification(self, detail):
      rubricComment = RubricComment.objects.get(id=detail)
      assignment = rubricComment.category.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricComment.category.assignment)
      self.assertEqual(assignment.feedbackStatus, 'live')
      self.assertFalse(assignment.collaborativeRubricMode)
      self.assertNotIn(assignment.state, ('published', 'closed'))

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)
