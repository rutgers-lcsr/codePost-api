# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
A category with no category-level testScript (tests that carry their own testCode) is a
supported configuration: run_suite runs each of its tests individually through run_test.
Once this crashed the whole run with UnboundLocalError and lost every category's results.
"""
from unittest import mock

import factory
from django.db.models.signals import post_save
from django.test import TestCase as DjangoTestCase

from autograder.services.TestService import TestService
from core.models import SubmissionTest, TestCase
from core.tests.factories import CourseFactory, TestCategoryFactory


def _exec_result(*names):
  return {
    "success": True,
    "stdout": "",
    "stderr": "",
    "output_data": {},
    "execution_time": 0.1,
    "cached": False,
    "error": None,
    "tests": [
      {"name": n, "passed": True, "score": 2, "max_score": 2, "status": "passed"} for n in names
    ],
  }


class CategoryWithoutTestScriptTests(DjangoTestCase):
  def setUp(self):
    with factory.django.mute_signals(post_save):
      self.course = CourseFactory(name="ag-legacy", period="s2026", organization__name="LegacyOrg")
      self.assignment = self.course.assignments.first()
      self.category = TestCategoryFactory(assignment=self.assignment, testScript="")
      self.first = TestCase.objects.create(
        testCategory=self.category, functionName="test_first", description="first", type="script",
        pointsPass=2, testCode="@test(name='test_first')\ndef test_first():\n    pass\n")
      self.second = TestCase.objects.create(
        testCategory=self.category, functionName="test_second", description="second", type="script",
        pointsPass=2, testCode="@test(name='test_second')\ndef test_second():\n    pass\n")
      self.submission = self.assignment.submissions.first()

  def test_each_test_runs_individually_and_saves_its_own_result(self):
    def fake_exec(file, test_case, user_id=None, file_overrides=None, test_function="__DEFAULT__"):
      return _exec_result(test_case.functionName)

    with mock.patch.object(TestService, "_run_ephemeral_execution", side_effect=fake_exec) as run:
      results = TestService.run_suite(self.submission.id)

    self.assertEqual(run.call_count, 2)
    self.assertEqual(sorted(r["testCaseId"] for r in results), sorted([self.first.id, self.second.id]))
    self.assertTrue(all(r["success"] for r in results), results)
    for test in (self.first, self.second):
      self.assertTrue(SubmissionTest.objects.get(submission=self.submission, testCase=test).passed)
