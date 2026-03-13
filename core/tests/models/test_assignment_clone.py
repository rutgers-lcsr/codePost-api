# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from core.models import (
    Assignment,
    AssignmentDataSet,
    AssignmentFile,
    Course,
    Organization,
    User,
    TestCase as AssignmentTestCase,
    TestCategory,
    TestCategoryResource,
)
from core.serializers.course import CourseSerializer
from core.utils import copy_assignment


class AssignmentCloneTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Clone Org", shortname="cloneorg")
        self.source_course = Course.objects.create(name="Source Course", period="F2026", organization=self.org)
        self.destination_course = Course.objects.create(name="Destination Course", period="S2027", organization=self.org)

        self.assignment = Assignment.objects.create(
            name="HW1",
            course=self.source_course,
            points=100,
            isReleased=True,
        )

        self.template_file = AssignmentFile.objects.create(
            assignment=self.assignment,
            name="helpers.py",
            extension=".py",
            data="def helper():\n    return 42\n",
            path="tests",
            required=False,
            description="Helper file",
        )

        self.dataset = AssignmentDataSet.objects.create(
            assignment=self.assignment,
            name="cases.csv",
            description="input cases",
            mount_path="shared/cases.csv",
            file=SimpleUploadedFile("cases.csv", b"x,y\n1,2\n"),
        )

        self.category = TestCategory.objects.create(
            assignment=self.assignment,
            name="Script Tests",
            testScript='@test(name="sum", points=5)\ndef test_sum():\n    assert 1 + 1 == 2\n',
            targetFileName="solution.py",
            sortKey=2,
            maxPoints=5,
        )

        AssignmentTestCase.objects.create(
            testCategory=self.category,
            description="sum test",
            type="script",
            pointsPass=5,
            pointsFail=0,
            testCode="assert 1 + 1 == 2",
            functionName="test_sum",
            timeout=15,
        )

        TestCategoryResource.objects.create(
            category=self.category,
            file=self.template_file,
            target_path="resources/helpers.py",
        )
        TestCategoryResource.objects.create(
            category=self.category,
            dataset=self.dataset,
            target_path="resources/cases.csv",
        )

    def test_copy_assignment_copies_test_script_and_resources(self):
        copied = copy_assignment(self.assignment, self.destination_course)

        self.assertIsNotNone(copied)
        copied_id = copied.id  # type: ignore[union-attr]
        copied = Assignment.objects.get(id=copied_id)
        self.assertEqual(copied.course.id, self.destination_course.id)

        copied_category = copied.testCategories.get(name="Script Tests")
        self.assertEqual(copied_category.testScript, self.category.testScript)
        self.assertEqual(copied_category.targetFileName, "solution.py")

        copied_resources = TestCategoryResource.objects.filter(category=copied_category).order_by("target_path")
        self.assertEqual(copied_resources.count(), 2)

        copied_file_resource = copied_resources.get(target_path="resources/helpers.py")
        self.assertIsNotNone(copied_file_resource.file)
        copied_file = copied_file_resource.file
        if copied_file is None:
            self.fail("Expected copied file resource to reference a file")
        self.assertEqual(copied_file.assignment.id, copied.id)
        self.assertEqual(copied_file.name, self.template_file.name)

        copied_dataset_resource = copied_resources.get(target_path="resources/cases.csv")
        self.assertIsNotNone(copied_dataset_resource.dataset)
        copied_dataset = copied_dataset_resource.dataset
        if copied_dataset is None:
            self.fail("Expected copied dataset resource to reference a dataset")
        self.assertEqual(copied_dataset.assignment.id, copied.id)
        self.assertEqual(copied_dataset.name, self.dataset.name)


class CourseCloneTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Course Clone Org", shortname="courseclone")
        self.source_course = Course.objects.create(name="Source", period="F2026", organization=self.org)

        self.user = User.objects.create_user(username="admin@clone.org", email="admin@clone.org", password="pw")
        self.user.profile.organization = self.org
        self.user.profile.canCreateCourses = True
        self.user.profile.canModifyRosters = True
        self.user.profile.save()

        self.source_course.courseAdmins.add(self.user)
        self.source_course.graders.add(self.user)

        assignment = Assignment.objects.create(name="Lab 1", course=self.source_course, points=10)
        helper = AssignmentFile.objects.create(
            assignment=assignment,
            name="helper.py",
            extension=".py",
            data="print('helper')",
        )
        category = TestCategory.objects.create(
            assignment=assignment,
            name="Autograder",
            testScript='@test(name="t", points=1)\ndef t():\n    assert True\n',
        )
        TestCategoryResource.objects.create(category=category, file=helper, target_path="helper.py")

    def test_course_serializer_clone_transfers_assignment_test_assets(self):
        request = APIRequestFactory().post("/courses/", {})
        request.user = self.user
        setattr(request, "auth", "a" * 40)

        serializer = CourseSerializer(
            data={"name": "Cloned", "period": "S2027", "cloneFrom": self.source_course.id},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        cloned_course = serializer.save()

        cloned_assignment = cloned_course.assignments.get(name="Lab 1")
        cloned_category = cloned_assignment.testCategories.get(name="Autograder")

        self.assertEqual(cloned_category.testScript, '@test(name="t", points=1)\ndef t():\n    assert True\n')
        self.assertEqual(cloned_category.resources.count(), 1)
        self.assertEqual(cloned_category.resources.first().target_path, "helper.py")
        self.assertEqual(cloned_category.resources.first().file.assignment_id, cloned_assignment.id)
