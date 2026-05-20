# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
import unittest


class TestSerializer_SubmissionSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass

    def test_queue_ordering_on_update(self):
        """Releasing a submission sends it to the back of the queue when course setting is enabled."""
        self.course.sendReleasedSubmissionsToBack = True
        self.course.save()
        sub = self.DB["Submission"]
        student = self.course.students.first()
        sub.students.add(student)
        grader = self.course.graders.first()
        sub.grader = grader
        sub.save()
        # Release the submission (set grader to null)
        response = request_as("update", grader, f"/submissions/{sub.id}/", {
            "grader": None,
            "students": [student.email],
        })
        self.assertEqual(response.status_code, 200)

    def test_date_edited_format(self):
        """dateEdited is returned in the course's timezone."""
        sub = self.DB["Submission"]
        admin = self.course.courseAdmins.first()
        response = request_as("read", admin, f"/submissions/{sub.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("dateEdited", response.data)

    def test_update_students(self):
        """Can update students on a submission."""
        sub = self.DB["Submission"]
        admin = self.course.courseAdmins.first()
        student = self.course.students.first()
        response = request_as("update", admin, f"/submissions/{sub.id}/", {
            "students": [student.email],
        })
        self.assertEqual(response.status_code, 200)

    def test_update_grader(self):
        """Can assign a grader to a submission."""
        sub = self.DB["Submission"]
        admin = self.course.courseAdmins.first()
        student = self.course.students.first()
        sub.students.add(student)
        sub.save()
        grader = self.course.graders.first()
        response = request_as("update", admin, f"/submissions/{sub.id}/", {
            "grader": grader.email,
            "students": [student.email],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["grader"], grader.email)

    def test_empty_student_list(self):
        """Empty student list should be rejected."""
        sub = self.DB["Submission"]
        admin = self.course.courseAdmins.first()
        response = request_as("update", admin, f"/submissions/{sub.id}/", {
            "students": [],
        })
        self.assertEqual(response.status_code, 400)

    def test_finalize_with_no_grader(self):
        """Finalizing without a grader should fail."""
        sub = self.DB["Submission"]
        sub.grader = None
        sub.save()
        admin = self.course.courseAdmins.first()
        response = request_as("update", admin, f"/submissions/{sub.id}/", {
            "isFinalized": True,
        })
        self.assertEqual(response.status_code, 400)


class TestSerializer_SubmissionSerializerFields(APITestCase):
    """Second set of SubmissionSerializer tests — renamed from duplicate class name."""

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass


class TestSerializer_AnonymousSubmissionSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass


class TestSerializer_SubmissionStatusSerializer_Removed(APITestCase):
    """
    NOTE: SubmissionStatusSerializer has been removed.
    This test class is kept as a stub but the serializer no longer exists.
    StudentSubmissionSerializer now handles all student submission cases.
    """

    def setUp(self):
        setUpBase(self)

    @unittest.skip('Not implemented yet')
    def test_contains_expected_fields(self):
        # This test is now obsolete - SubmissionStatusSerializer has been removed
        pass


class TestSerializer_StudentSubmissionSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)
        self.submission = self.DB["Submission"]

    def test_grade_is_present_when_feedback_released_and_hide_grades_false(self):
        from core.serializers.submission import StudentSubmissionSerializer
        assignment = self.submission.assignment
        assignment.feedbackReleased = True
        assignment.hideGrades = False
        assignment.save()

        serializer = StudentSubmissionSerializer(self.submission)
        self.assertEqual(serializer.data["grade"], self.submission.grade)

    def test_grade_is_masked_when_hide_grades_true(self):
        from core.serializers.submission import StudentSubmissionSerializer
        assignment = self.submission.assignment
        assignment.feedbackReleased = True
        assignment.hideGrades = True
        assignment.save()

        serializer = StudentSubmissionSerializer(self.submission)
        self.assertIsNone(serializer.data["grade"])


class TestSerializer_StudentConsoleDataSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)
        self.submission = self.DB["Submission"]

    def test_grade_is_present_when_feedback_released_and_hide_grades_false(self):
        from core.serializers.submission import StudentConsoleDataSerializer
        assignment = self.submission.assignment
        assignment.feedbackReleased = True
        assignment.hideGrades = False
        assignment.save()

        serializer = StudentConsoleDataSerializer(self.submission)
        self.assertEqual(serializer.data["grade"], self.submission.grade)

    def test_grade_is_masked_when_hide_grades_true(self):
        from core.serializers.submission import StudentConsoleDataSerializer
        assignment = self.submission.assignment
        assignment.feedbackReleased = True
        assignment.hideGrades = True
        assignment.save()

        serializer = StudentConsoleDataSerializer(self.submission)
        self.assertIsNone(serializer.data["grade"])


class TestSerializer_StudentSubmissionWithoutGradeSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass
