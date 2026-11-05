# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
TestService.run_suite is reached by students (the run endpoint, run-on-submit) with
whatever their code makes the executor report. These tests pin that a student-triggered
run can only write that student's own results: it never creates or deletes instructor
TestCases, never swaps in instructor resource files, and never ingests result files the
student uploaded.
"""
from unittest import mock

import factory
from django.db.models.signals import post_save
from django.test import TestCase as DjangoTestCase

from autograder.services.TestService import TestService
from autograder.services.executors.base import ExecutionResult
from core.models import AssignmentFile, SubmissionFile, SubmissionTest, TestCase, TestCategoryResource
from core.tests.factories import CourseFactory, SubmissionFactory, TestCategoryFactory

SCRIPT = "@test(name='test_real')\ndef test_real():\n    pass\n"


def _result(*names_and_max, success=True):
  return {
    "success": success,
    "stdout": "",
    "stderr": "",
    "output_data": {},
    "execution_time": 0.1,
    "cached": False,
    "error": None,
    "tests": [
      {"name": n, "passed": True, "score": m, "max_score": m, "status": "passed"}
      for n, m in names_and_max
    ],
  }


class _SuiteBase(DjangoTestCase):
  def setUp(self):
    with factory.django.mute_signals(post_save):
      self.course = CourseFactory(name="ag-integrity", period="s2026", organization__name="IntegrityOrg")
      self.assignment = self.course.assignments.first()
      self.category = TestCategoryFactory(assignment=self.assignment, testScript=SCRIPT)
      self.real = TestCase.objects.create(
        testCategory=self.category, functionName="test_real", description="real", type="script", pointsPass=5)
      self.stale = TestCase.objects.create(
        testCategory=self.category, functionName="test_other", description="other", type="script", pointsPass=3)
      self.submission = self.assignment.submissions.first()
      self.other_submission = SubmissionFactory(assignment=self.assignment)
      SubmissionTest.objects.create(
        submission=self.other_submission, testCase=self.stale, passed=True, score=3, maxScore=3, logs="ok")
    self.student = self.course.students.first()
    self.admin = self.course.courseAdmins.first()

  def run_suite_with(self, result, user_id, **kwargs):
    with mock.patch.object(TestService, "_run_ephemeral_execution", return_value=result):
      return TestService.run_suite(self.submission.id, user_id=user_id, **kwargs)


class StudentRunCannotEditTestCasesTests(_SuiteBase):
  def test_student_run_reporting_only_some_tests_keeps_other_tests_and_other_students_results(self):
    self.run_suite_with(_result(("test_real", 5)), str(self.student.id))

    self.assertTrue(TestCase.objects.filter(id=self.stale.id).exists(), "instructor TestCase deleted by a student run")
    self.assertTrue(SubmissionTest.objects.filter(
      submission=self.other_submission, testCase=self.stale).exists(), "another student's result was cascade-deleted")
    self.assertTrue(SubmissionTest.objects.get(submission=self.submission, testCase=self.real).passed)

  def test_student_run_reporting_an_unknown_test_name_creates_no_testcase(self):
    self.run_suite_with(_result(("test_real", 5), ("bonus_free_points", 999)), str(self.student.id))

    self.assertEqual(
      set(self.category.testCases.values_list("functionName", flat=True)), {"test_real", "test_other"})

  def test_run_on_submit_without_a_user_cannot_edit_testcases(self):
    self.run_suite_with(_result(("test_real", 5), ("bonus_free_points", 9)), None)

    self.assertEqual(
      set(self.category.testCases.values_list("functionName", flat=True)), {"test_real", "test_other"})


class AdminRunStillSyncsTestCasesTests(_SuiteBase):
  def test_admin_run_creates_new_tests_and_deletes_stale_ones(self):
    self.run_suite_with(_result(("test_real", 5), ("test_new", 2)), str(self.admin.id))

    self.assertEqual(
      set(self.category.testCases.values_list("functionName", flat=True)), {"test_real", "test_new"})

  def test_admin_run_that_returns_no_results_does_not_wipe_the_tests(self):
    self.run_suite_with(_result(), str(self.admin.id))

    self.assertEqual(self.category.testCases.count(), 2)


class FileOverrideScopeTests(_SuiteBase):
  def setUp(self):
    super().setUp()
    with factory.django.mute_signals(post_save):
      self.resource_file = AssignmentFile.objects.create(
        assignment=self.assignment, name="expected.txt", extension=".txt", data="INSTRUCTOR")
      TestCategoryResource.objects.create(
        category=self.category, file=self.resource_file, target_path="expected.txt")
    self.student_file = self.submission.files.first()

  def _factory_calls(self, user_id, overrides):
    fake_executor = mock.Mock()
    fake_executor.execute.return_value = ExecutionResult(success=True, tests=[])
    with mock.patch("autograder.services.TestService.Executor.factory", return_value=fake_executor) as factory_mock:
      TestService.run_suite(self.submission.id, user_id=user_id, file_overrides=overrides)
    return factory_mock.call_args.kwargs

  def test_student_cannot_override_instructor_resource_file(self):
    kwargs = self._factory_calls(str(self.student.id), {self.resource_file.id: "STUDENT"})

    contents = [r.get("content") for r in kwargs["resources"]]
    self.assertEqual(contents, ["INSTRUCTOR"])

  def test_student_cannot_inject_an_instructor_file_as_additional_file(self):
    kwargs = self._factory_calls(str(self.student.id), {self.resource_file.id: "STUDENT"})

    self.assertEqual(kwargs["additional_files"], {})

  def test_student_can_still_override_their_own_submission_file(self):
    kwargs = self._factory_calls(str(self.student.id), {self.student_file.id: "print('unsaved edit')"})

    self.assertEqual(kwargs["content_override"], "print('unsaved edit')")

  def test_student_cannot_override_a_file_of_another_submission(self):
    other_file = self.other_submission.files.first()
    kwargs = self._factory_calls(str(self.student.id), {other_file.id: "STUDENT"})

    self.assertEqual(kwargs["additional_files"], {})
    self.assertIsNone(kwargs["content_override"])

  def test_admin_can_still_override_a_resource_file(self):
    kwargs = self._factory_calls(str(self.admin.id), {self.resource_file.id: "EDITED"})

    self.assertEqual([r.get("content") for r in kwargs["resources"]], ["EDITED"])


class UploadedResultFileTests(_SuiteBase):
  def test_student_uploaded_test_result_file_does_not_create_results(self):
    with factory.django.mute_signals(post_save):
      other_category = TestCategoryFactory(assignment=self.assignment, name="Planted", testScript=SCRIPT)
      planted = TestCase.objects.create(
        testCategory=other_category, functionName="test_b", description="b", type="script", pointsPass=4)
      SubmissionFile.objects.create(
        submission=self.submission, name="_test_Planted.txt", extension=".txt", data="test_b,true,9999")

    # Only the first category runs; nothing in this run reports test_b.
    self.run_suite_with(_result(("test_real", 5)), str(self.student.id), test_case_ids=[self.real.id])

    self.assertFalse(SubmissionTest.objects.filter(submission=self.submission, testCase=planted).exists())
