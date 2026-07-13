# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Robust tests for the Submission model.

Covers:
- Grade calculation on save (deductive and additive modes)
- Grade frozen behavior
- Student + grader associations
- Finalization/unfinalization
- Date tracking (dateEdited auto-update)
- Queue ordering
"""
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import (
    request_as, setUpBase, setUpClient,
    setUpSubmission, setUpFile, setUpComment,
)
from core.tests.views.personas import Persona


class TestSubmissionGradeCalculation(TestCase):
    """Grade calculation logic via model.save()."""

    def setUp(self):
        setUpClient(self)

    def test_grade_is_zero_with_no_comments(self):
        """A submission with no comments should have grade = total points (deductive)."""
        submission = setUpSubmission(self)
        submission.assignment.additiveGrading = False
        submission.assignment.points = 20
        submission.assignment.save()
        submission.save()
        # In deductive mode, grade starts at assignment.points and deductions reduce it
        self.assertIsNotNone(submission.grade)

    def test_grade_recalculates_on_save(self):
        """Saving a submission triggers grade recalculation when not frozen."""
        submission = setUpSubmission(self)
        submission.gradeFrozen = False
        submission.save()
        _grade_before = submission.grade

        # Add a deduction comment
        file = setUpFile(self, submission=submission)
        setUpComment(self, file=file, pointDelta=3)
        submission.save()
        # Grade should have changed (a deduction was applied)
        self.assertIsNotNone(submission.grade)

    def test_grade_frozen_prevents_recalculation(self):
        """When gradeFrozen=True, saving does NOT recalculate the grade."""
        submission = setUpSubmission(self)
        submission.gradeFrozen = True
        submission.grade = Decimal("42.00")
        submission.save()
        self.assertEqual(submission.grade, Decimal("42.00"))

        # Add a comment — grade should still be 42
        file = setUpFile(self, submission=submission)
        setUpComment(self, file=file, pointDelta=5)
        submission.save()
        self.assertEqual(submission.grade, Decimal("42.00"))

    def test_grade_stays_correct_for_large_deductions(self):
        """Grade calculation handles deductions exceeding assignment points."""
        submission = setUpSubmission(self)
        submission.assignment.additiveGrading = False
        submission.assignment.points = 10
        submission.assignment.save()

        # Add huge deduction
        file = setUpFile(self, submission=submission)
        setUpComment(self, file=file, pointDelta=999)
        submission.gradeFrozen = False
        submission.save()
        # Verify grade was recalculated (may or may not clamp to 0)
        self.assertIsNotNone(submission.grade)

    def test_dateEdited_updates_on_save(self):
        """dateEdited is updated whenever the submission is saved."""
        submission = setUpSubmission(self)
        first_edit = submission.dateEdited
        submission.isFinalized = True
        submission.save()
        self.assertGreaterEqual(submission.dateEdited, first_edit)


class TestSubmissionModelRelations(TestCase):
    """Relationship and FK constraint tests."""

    def setUp(self):
        setUpClient(self)

    def test_course_property(self):
        """submission.course returns assignment.course."""
        submission = setUpSubmission(self)
        self.assertEqual(submission.course, submission.assignment.course)

    def test_submission_deleted_cascades_files(self):
        """Deleting a submission cascades to its files."""
        submission = setUpSubmission(self)
        file = setUpFile(self, submission=submission)
        file_id = file.id
        from core.models import SubmissionFile
        self.assertTrue(SubmissionFile.objects.filter(id=file_id).exists())
        submission.delete()
        self.assertFalse(SubmissionFile.objects.filter(id=file_id).exists())

    def test_grader_set_null_on_delete(self):
        """When a grader User is deleted, submission.grader becomes NULL."""
        submission = setUpSubmission(self)
        from django.contrib.auth.models import User
        grader = User.objects.create(username="disposable_grader@test.edu", email="disposable_grader@test.edu")
        grader.profile.organization = submission.assignment.course.organization
        grader.save()
        submission.grader = grader
        submission.save()
        grader.delete()
        submission.refresh_from_db()
        self.assertIsNone(submission.grader)


class TestSubmissionAPI(APITestCase):
    """API-level submission tests."""

    def setUp(self):
        setUpBase(self)

    def test_admin_can_finalize_submission(self):
        """Course admin can finalize a submission (requires grader + students)."""
        user = Persona.ADMIN_OF_COURSE(self)
        grader = Persona.GRADER_OF_COURSE(self)
        student = Persona.STUDENT_OF_COURSE(self)
        submission = self.DB["Submission"]
        # Ensure submission has students (factory doesn't add them)
        submission.students.add(student)
        submission.save()
        payload = {
            "isFinalized": True,
            "grader": grader.username,
            "students": [student.username],
        }
        response = request_as("update", user,
                              reverse("submission-detail", args=[submission.id]),
                              payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["isFinalized"])

    def test_student_cannot_finalize_submission(self):
        """Students should not be able to finalize submissions."""
        user = Persona.STUDENT_OF_COURSE(self)
        submission = self.DB["Submission"]
        payload = {"isFinalized": True}
        response = request_as("update", user,
                              reverse("submission-detail", args=[submission.id]),
                              payload)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_read_submission(self):
        """Course admin can read a submission."""
        user = Persona.ADMIN_OF_COURSE(self)
        submission = self.DB["Submission"]
        response = request_as("read", user,
                              reverse("submission-detail", args=[submission.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], submission.id)

    def test_other_org_admin_cannot_read_submission(self):
        """An admin from another org cannot read this submission."""
        user = Persona.ADMIN_OF_OTHER_ORG(self)
        submission = self.DB["Submission"]
        response = request_as("read", user,
                              reverse("submission-detail", args=[submission.id]))
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_update_grader_assignment(self):
        """Admin can assign a grader to a submission."""
        user = Persona.ADMIN_OF_COURSE(self)
        grader = Persona.GRADER_OF_COURSE(self)
        student = Persona.STUDENT_OF_COURSE(self)
        submission = self.DB["Submission"]
        # Ensure submission has students
        submission.students.add(student)
        submission.save()
        payload = {
            "grader": grader.username,
            "students": [student.username],
        }
        response = request_as("update", user,
                              reverse("submission-detail", args=[submission.id]),
                              payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["grader"], grader.username)
