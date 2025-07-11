from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass
from core.tests.views.personas import Persona

from core.tests.views.results.rubricComment import PERMISSIONS

from core.models import *


class TestPermissions_RubricComment_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)


class TestPermissions_RubricComment_Released(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.save()

    def assertModification(self, detail):
      rubricComment = RubricComment.objects.get(id=detail)
      assignment = rubricComment.category.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricComment.category.assignment)
      self.assertTrue(assignment.isReleased)
      self.assertFalse(assignment.collaborativeRubricMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_RubricComment_CollaborativeRubric(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

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
      self.assertFalse(assignment.isReleased)
      self.assertTrue(assignment.collaborativeRubricMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_RubricComment_ReleasedCollaborativeRubric(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.collaborativeRubricMode = True
      assignment.save()

    def assertModification(self, detail):
      rubricComment = RubricComment.objects.get(id=detail)
      assignment = rubricComment.category.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricComment.category.assignment)
      self.assertTrue(assignment.isReleased)
      self.assertTrue(assignment.collaborativeRubricMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_RubricComment_LiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    # Extra check on our manual results
    self.assertDictEqual(PERMISSIONS["PERMISSIONS_LIVEFEEDBACK"],
                         PERMISSIONS["PERMISSIONS_RELEASED"])

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.liveFeedbackMode = True
      assignment.save()

    def assertModification(self, detail):
      rubricComment = RubricComment.objects.get(id=detail)
      assignment = rubricComment.category.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricComment.category.assignment)
      self.assertTrue(assignment.liveFeedbackMode)
      self.assertFalse(assignment.collaborativeRubricMode)
      self.assertFalse(assignment.isReleased)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)
