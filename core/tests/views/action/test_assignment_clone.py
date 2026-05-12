# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from typing import Any, cast

from core.models import (
    Assignment,
    AssignmentDataSet,
    AssignmentFile,
    TestCategory,
    TestCategoryResource,
)
from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona


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
