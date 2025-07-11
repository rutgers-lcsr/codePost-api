from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass
from core.tests.views.personas import Persona

from core.models import *
from core.tests.views.results.comment import PERMISSIONS


class TestPermissions_Comment_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)


class TestPermissions_Comment_Finalized(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

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

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.save()

    def assertModification(self, detail):
      comment = Comment.objects.get(id=detail)
      submission = comment.file.submission
      assignment = submission.assignment
      self.assertFalse(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Comment_FinalizedReleased(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

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
      assignment = submission.assignment
      self.assertTrue(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Comment_ReleasedLiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = True
      assignment.liveFeedbackMode = True
      assignment.save()

    def assertModification(self, detail):
      comment = Comment.objects.get(id=detail)
      submission = comment.file.submission
      assignment = submission.assignment
      self.assertFalse(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)
      self.assertTrue(submission.assignment.liveFeedbackMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Comment_UnreleasedLiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    # Extra check on our manual results
    self.assertDictEqual(PERMISSIONS["PERMISSIONS_UNRELEASEDLIVEFEEDBACK"],
                         PERMISSIONS["PERMISSIONS_RELEASEDLIVEFEEDBACK"])
    self.assertDictEqual(PERMISSIONS["PERMISSIONS_UNRELEASEDLIVEFEEDBACK"], PERMISSIONS["PERMISSIONS_RELEASED"])

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.isReleased = False
      assignment.liveFeedbackMode = True
      assignment.save()

    def assertModification(self, detail):
      comment = Comment.objects.get(id=detail)
      submission = comment.file.submission
      assignment = submission.assignment
      self.assertFalse(submission.isFinalized)
      self.assertFalse(submission.assignment.isReleased)
      self.assertTrue(submission.assignment.liveFeedbackMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_Comment_FinalizedReleasedDontHideGraders(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

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
      assignment = submission.assignment
      self.assertTrue(submission.isFinalized)
      self.assertTrue(submission.assignment.isReleased)
      self.assertFalse(submission.assignment.hideGradersFromStudents)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)
