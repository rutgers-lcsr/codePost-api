# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from typing import Any, cast

from core.models import (
    Assignment,
    AssignmentDataSet,
    AssignmentFile,
    Question,
    QuestionBank,
    Quiz,
    TestCategory,
    TestCategoryResource,
)
from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona
from core.tests.views.quiz_helpers import _add, _bank, _mc, _quiz


class TestPermissions_Assignment_Clone(APITestCase):

  def setUp(self):
    setUpBase(self)

    db = cast(dict[str, Any], self.DB)
    self.assignment = Assignment.objects.get(id=db["Assignment"].id)

    self.helper_file = AssignmentFile.objects.create(
      assignment=self.assignment,
      name="helper_clone_test.py",
      extension=".py",
      data="def helper():\n    return 1\n",
      path="tests",
      required=False,
      description="helper for clone action test",
    )

    self.dataset = AssignmentDataSet.objects.create(
      assignment=self.assignment,
      name="clone_cases.csv",
      description="dataset for clone action",
      mount_path="shared/clone_cases.csv",
      file=SimpleUploadedFile("clone_cases.csv", b"x,y\n1,2\n"),
    )

    self.category = TestCategory.objects.create(
      assignment=self.assignment,
      name="Clone Script Category",
      testScript='@test(name="clone-test", points=3)\ndef clone_test():\n    assert True\n',
      targetFileName="solution.py",
      maxPoints=3,
    )

    TestCategoryResource.objects.create(
      category=self.category,
      file=self.helper_file,
      target_path="resources/helper_clone_test.py",
    )
    TestCategoryResource.objects.create(
      category=self.category,
      dataset=self.dataset,
      target_path="resources/clone_cases.csv",
    )

  def test_assignment_clone_endpoint_copies_test_assets(self):
    admin = Persona.ADMIN_OF_COURSE(self)
    endpoint = reverse("assignment-clone", args=[self.assignment.id])

    response = cast(Any, request_as("create", admin, endpoint, {}))
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    cloned_assignment = Assignment.objects.get(id=response.data["id"])
    cloned_category = cloned_assignment.testCategories.get(name="Clone Script Category")

    self.assertEqual(cloned_category.testScript, self.category.testScript)
    self.assertEqual(cloned_category.targetFileName, "solution.py")

    resources = TestCategoryResource.objects.filter(category=cloned_category).order_by("target_path")
    self.assertEqual(resources.count(), 2)

    file_resource = resources.get(target_path="resources/helper_clone_test.py")
    self.assertIsNotNone(file_resource.file)
    if file_resource.file is None:
      self.fail("Expected cloned file resource to include file")
    self.assertEqual(file_resource.file.assignment.id, cloned_assignment.id)

    dataset_resource = resources.get(target_path="resources/clone_cases.csv")
    self.assertIsNotNone(dataset_resource.dataset)
    if dataset_resource.dataset is None:
      self.fail("Expected cloned dataset resource to include dataset")
    self.assertEqual(dataset_resource.dataset.assignment.id, cloned_assignment.id)

  def test_assignment_clone_endpoint_forbidden_for_non_admin(self):
    grader = Persona.GRADER_OF_COURSE(self)
    endpoint = reverse("assignment-clone", args=[self.assignment.id])

    response = cast(Any, request_as("create", grader, endpoint, {}))
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def _attach_quiz(self):
    bank = _bank(self.course)
    question = _mc(self.course, bank)
    quiz = _quiz(self.course, title="Attached Quiz", assignment=self.assignment, isPublished=True)
    _add(quiz, question, sortKey=1)
    return bank, question, quiz

  def test_clone_same_course_reuses_questions(self):
    bank, question, quiz = self._attach_quiz()
    admin = Persona.ADMIN_OF_COURSE(self)
    endpoint = reverse("assignment-clone", args=[self.assignment.id])

    question_count = Question.objects.count()
    bank_count = QuestionBank.objects.count()

    response = cast(Any, request_as("create", admin, endpoint, {}))
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    cloned_assignment = Assignment.objects.get(id=response.data["id"])
    cloned_quiz = Quiz.objects.get(assignment=cloned_assignment)
    self.assertNotEqual(cloned_quiz.id, quiz.id)
    self.assertFalse(cloned_quiz.isPublished)
    # Same-course clones link the SAME question rows — no content duplication.
    self.assertEqual(cloned_quiz.quizQuestions.get().question_id, question.id)
    self.assertEqual(Question.objects.count(), question_count)
    self.assertEqual(QuestionBank.objects.count(), bank_count)

  def test_clone_cross_course_copies_banks_and_resets_draft(self):
    bank, question, quiz = self._attach_quiz()
    admin = Persona.ADMIN_OF_COURSE(self)
    self.other_course.courseAdmins.add(admin)
    endpoint = reverse("assignment-clone", args=[self.assignment.id])

    response = cast(Any, request_as("create", admin, endpoint, {"course": self.other_course.id}))
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    cloned_assignment = Assignment.objects.get(id=response.data["id"])
    self.assertEqual(cloned_assignment.course_id, self.other_course.id)

    cloned_quiz = Quiz.objects.get(assignment=cloned_assignment)
    self.assertEqual(cloned_quiz.course_id, self.other_course.id)
    self.assertFalse(cloned_quiz.isPublished)

    cloned_bank = QuestionBank.objects.get(course=self.other_course)
    self.assertEqual(cloned_bank.name, bank.name)
    cloned_question = cloned_quiz.quizQuestions.get().question
    self.assertEqual(cloned_question.course_id, self.other_course.id)
    self.assertEqual(cloned_question.bank_id, cloned_bank.id)
    self.assertNotEqual(cloned_question.id, question.id)

  def test_clone_cross_course_bank_name_collision(self):
    bank, _question, _quiz_obj = self._attach_quiz()
    QuestionBank.objects.create(course=self.other_course, name=bank.name)
    admin = Persona.ADMIN_OF_COURSE(self)
    self.other_course.courseAdmins.add(admin)
    endpoint = reverse("assignment-clone", args=[self.assignment.id])

    response = cast(Any, request_as("create", admin, endpoint, {"course": self.other_course.id}))
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    self.assertTrue(QuestionBank.objects.filter(
      course=self.other_course, name=f"{bank.name} (copy 1)").exists())
