# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.tests.views.permissions_base import BaseTestCases, initPermissionsClass

from core.models import *

from core.tests.views.results.rubricCategory import PERMISSIONS


class TestPermissions_RubricCategory_Base(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)
    super().__init__(*args, model=self.model, permissions=self.permissions, **kwargs)


class TestPermissions_RubricCategory_Released(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      # Students see rubric categories once feedback is released (Phase 4 gate)
      assignment.state = 'published'
      assignment.feedbackStatus = 'released'
      assignment.save()

    def assertModification(self, detail):
      rubricCategory = RubricCategory.objects.get(id=detail)
      assignment = rubricCategory.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricCategory.assignment)
      self.assertEqual(assignment.state, 'published')
      self.assertFalse(assignment.collaborativeRubricMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_RubricCategory_CollaborativeRubric(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.collaborativeRubricMode = True
      assignment.save()

    def assertModification(self, detail):
      rubricCategory = RubricCategory.objects.get(id=detail)
      assignment = rubricCategory.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricCategory.assignment)
      self.assertNotIn(assignment.state, ('published', 'closed'))
      self.assertTrue(assignment.collaborativeRubricMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_RubricCategory_ReleasedCollaborativeRubric(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.state = 'published'
      assignment.feedbackStatus = 'released'
      assignment.collaborativeRubricMode = True
      assignment.save()

    def assertModification(self, detail):
      rubricCategory = RubricCategory.objects.get(id=detail)
      assignment = rubricCategory.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricCategory.assignment)
      self.assertEqual(assignment.state, 'published')
      self.assertTrue(assignment.collaborativeRubricMode)

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)


class TestPermissions_RubricCategory_LiveFeedback(BaseTestCases.TestPermissions):

  def __init__(self, *args, **kwargs):
    initPermissionsClass(self)

    # Extra check on our manual results
    self.assertDictEqual(PERMISSIONS["PERMISSIONS_LIVEFEEDBACK"],
                         PERMISSIONS["PERMISSIONS_RELEASED"])

    def modifier(self):
      submission = Submission.objects.filter(assignment__course=self.course).first()
      assignment = submission.assignment
      assignment.feedbackStatus = 'live'
      assignment.save()

    def assertModification(self, detail):
      rubricCategory = RubricCategory.objects.get(id=detail)
      assignment = rubricCategory.assignment
      submission = Submission.objects.filter(assignment__course=self.course).first()
      self.assertEqual(submission.assignment, rubricCategory.assignment)
      self.assertEqual(assignment.feedbackStatus, 'live')
      self.assertFalse(assignment.collaborativeRubricMode)
      self.assertNotIn(assignment.state, ('published', 'closed'))

    super().__init__(*args, model=self.model, permissions=self.permissions,
                     modifier=modifier, assertModification=assertModification, **kwargs)
