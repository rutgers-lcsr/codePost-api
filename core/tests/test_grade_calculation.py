# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.models import calculate_grade, TestCategory, TestCase as AutograderTestCase, SubmissionTest
from django.test import TestCase
from core.tests.utils import setUpClient, setUpSubmission, setUpFile, setUpRubricComment, setUpRubricCategory, setUpComment
import random
import decimal

##########################################################################
##################################################### Helper functions ###
##########################################################################


def setUpFileAndComments(self, submission, genericPts, name, path, rubricComment):
  file = setUpFile(self, name=name, path=path, submission=submission)
  _comment1 = setUpComment(self, file=file, pointDelta=0)
  _comment2 = setUpComment(self, file=file, pointDelta=genericPts)
  _comment3 = setUpComment(self, file=file, rubricComment=rubricComment, pointDelta=random.randint(1, 100))
  return file


def setUpSubmissionWithFiles(self, additiveGrading, assignmentPts, f1Pts, f1RubricPts, f2Pts, f2RubricPts, rubricLimit, testOld, testPath):
  submission = setUpSubmission(self)
  submission.assignment.additiveGrading = additiveGrading
  submission.assignment.points = assignmentPts

  # Set up rubric
  rubricCategory = setUpRubricCategory(self, pointLimit=rubricLimit, assignment=submission.assignment)
  rubricComment1 = setUpRubricComment(self, category=rubricCategory, pointDelta=f1RubricPts)
  rubricComment2 = setUpRubricComment(self, category=rubricCategory, pointDelta=f2RubricPts)

  # Set up files
  (file1Name, file2Name) = ('file1.java', 'file1.java') if testOld else ('file1.java', 'file2.java')
  (file1Path, file2Path) = ('src', 'src') if (testPath and testOld) else ('src', 'tst') if (testPath) else ('', '')
  _file1 = setUpFileAndComments(self, submission=submission, genericPts=f1Pts,
                               name=file1Name, path=file1Path, rubricComment=rubricComment1)
  _file2 = setUpFileAndComments(self, submission=submission, genericPts=f2Pts,
                               name=file2Name, path=file2Path, rubricComment=rubricComment2)

  return submission


def base_test(self, additiveGrading, categoryLimit, testOld, testPath, expectedGrade):
  ptsMultiplier = -1 if additiveGrading else 1
  submission = setUpSubmissionWithFiles(self, additiveGrading=additiveGrading, assignmentPts=assignmentPts, f1Pts=ptsMultiplier * f1Pts, f1RubricPts=ptsMultiplier *
                                        f1RubricPts, f2Pts=ptsMultiplier * f2Pts, f2RubricPts=ptsMultiplier * f2RubricPts, rubricLimit=categoryLimit, testOld=testOld, testPath=testPath)
  self.assertEqual(calculate_grade(submission), decimal.Decimal(expectedGrade))


##########################################################################
##################################################### Test constants  ####
##########################################################################

(f1Pts, f2Pts) = (5, 10)
(f1RubricPts, f2RubricPts) = (4, 2)
assignmentPts = 100

##########################################################################
# Base Case (No File v
##########################################################################


class NoCaps_NoOld(TestCase):

  def setUp(self):
    setUpClient(self)

  def test_deductive(self, paths=False):
    # Inputs
    (additiveGrading, categoryLimit, testOld, testPath) = (False, None, False, paths)
    # Expected output: Full points subtracted from assignment total
    expectedGrade = assignmentPts - (f1Pts + f2Pts + f1RubricPts + f2RubricPts)
    ### Run Test ####
    base_test(self, additiveGrading, categoryLimit, testOld, testPath, expectedGrade)

  def test_additive(self, paths=False):
    # Inputs
    (additiveGrading, categoryLimit, testOld, testPath) = (True, None, False, paths)
    # Expected output: Full points
    expectedGrade = (f1Pts + f2Pts + f1RubricPts + f2RubricPts)
    ### Run Test ###
    base_test(self, additiveGrading, categoryLimit, testOld, testPath, expectedGrade)


class Caps_NoOld(TestCase):

  def setUp(self):
    setUpClient(self)

  def test_deductive(self, paths=False):
    # Inputs
    (additiveGrading, categoryLimit, testOld, testPath) = (False, 3, False, paths)
    # Expected output: Capped points subtracted from assignment total
    expectedGrade = (assignmentPts - (f1Pts + f2Pts + min(categoryLimit, f1RubricPts + f2RubricPts)))
    ### Run Test ###
    base_test(self, additiveGrading, categoryLimit, testOld, testPath, expectedGrade)

  def test_additive(self, paths=False):
    # Inputs
    (additiveGrading, categoryLimit, testOld, testPath) = (True, -3, False, paths)
    # Expected output: Cappted points
    expectedGrade = (f1Pts + f2Pts + min(-categoryLimit, f1RubricPts + f2RubricPts))
    ### Run Test ###
    base_test(self, additiveGrading, categoryLimit, testOld, testPath, expectedGrade)

# Testing with paths: Should be the same behavi


class NoCaps_NoOld_Paths(TestCase):

  def setUp(self):
    setUpClient(self)

  def test_deductive(self):
    NoCaps_NoOld.test_deductive(self, True)

  def test_additive(self, paths=False):
    NoCaps_NoOld.test_additive(self, True)


class Caps_NoOld_Paths(TestCase):

  def setUp(self):
    setUpClient(self)

  def test_deductive(self):
    Caps_NoOld.test_deductive(self, True)

  def test_additive(self, paths=False):
    Caps_NoOld.test_additive(self, True)

##########################################################################
# File versioning test
##########################################################################


class NoCaps_Old(TestCase):

  def setUp(self):
    setUpClient(self)

  def test_deductive(self, paths=False):
    # Inputs
    (additiveGrading, categoryLimit, testOld, testPath) = (False, None, True, paths)
    # Expected output: Only the second file's points deducted from total assignment points
    expectedGrade = assignmentPts - (f2Pts + f2RubricPts)
    ### Run Test ###
    base_test(self, additiveGrading, categoryLimit, testOld, testPath, expectedGrade)

  def test_additive(self, paths=False):
    # Inputs
    (additiveGrading, categoryLimit, testOld, testPath) = (True, None, True, paths)
    # Expected output: Only the second file's points
    expectedGrade = f2Pts + f2RubricPts
    ### Run Test ###
    base_test(self, additiveGrading, categoryLimit, testOld, testPath, expectedGrade)


class Caps_Old(TestCase):

  def setUp(self):
    setUpClient(self)

  def test_deductive(self, paths=False):
    # Inputs
    (additiveGrading, categoryLimit, testOld, testPath) = (False, 3, True, paths)
    # Expected output: Capped second file points subtracted from total assignment points
    expectedGrade = assignmentPts - (f2Pts + min(categoryLimit, f2RubricPts))
    ### Run Test ###
    base_test(self, additiveGrading, categoryLimit, testOld, testPath, expectedGrade)

  def test_additive(self, paths=False):
    # Inputs
    (additiveGrading, categoryLimit, testOld, testPath) = (True, -3, True, paths)
    # Expected output: Capped second file points
    expectedGrade = f2Pts + min(-categoryLimit, f2RubricPts)
    ### Run Test ###
    base_test(self, additiveGrading, categoryLimit, testOld, testPath, expectedGrade)

# Testing with paths: Should be the same behavi


class NoCaps_Old_Paths(TestCase):

  def setUp(self):
    setUpClient(self)

  def test_deductive(self):
    NoCaps_Old.test_deductive(self, True)

  def test_additive(self, paths=False):
    NoCaps_Old.test_additive(self, True)


class Caps_Old_Paths(TestCase):

  def setUp(self):
    setUpClient(self)

  def test_deductive(self):
    Caps_Old.test_deductive(self, True)

  def test_additive(self, paths=False):
    Caps_Old.test_additive(self, True)


class ScriptTestScoreAggregation(TestCase):

  def setUp(self):
    setUpClient(self)

  def test_partial_score_counts_even_when_points_pass_is_zero(self):
    submission = setUpSubmission(self)
    assignment = submission.assignment
    assignment.additiveGrading = True
    assignment.testsAffectGrade = True
    assignment.save()

    category = TestCategory.objects.create(assignment=assignment, name="Script Category")
    test_case = AutograderTestCase.objects.create(
      testCategory=category,
      description="Partial test",
      type='script',
      pointsPass=0,
      pointsFail=0,
      functionName='test_partial',
    )

    SubmissionTest.objects.create(
      submission=submission,
      testCase=test_case,
      logs='partial credit',
      passed=False,
      isError=False,
      score=decimal.Decimal('2.50'),
      maxScore=decimal.Decimal('5.00'),
    )

    self.assertEqual(calculate_grade(submission), decimal.Decimal('2.50'))
