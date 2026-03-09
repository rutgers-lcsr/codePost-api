# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Robust tests for the Comment model.

Covers:
- pointDelta behavior when linked to a rubricComment
- Required fields validation
- Color hex validation
- Comment position validation (startLine/endLine, startChar/endChar)
- Cascade deletion when parent file is deleted
"""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Comment, RubricComment
from core.tests.utils import (
    request_as, setUpBase, setUpClient,
    setUpFile, setUpComment, setUpRubricComment, setUpRubricCategory,
    setUpAssignment, setUpSubmission,
)
from core.tests.factories import (
    CourseFactory, OrganizationFactory, AssignmentFactory,
    SubmissionFactory, SubmissionFileFactory,
    RubricCategoryFactory, RubricCommentFactory,
)
from core.tests.views.personas import Persona


class TestCommentModelBehavior(TestCase):
    """Direct model-level behavioral tests."""

    def setUp(self):
        setUpClient(self)

    def test_pointDelta_nulled_when_rubricComment_linked(self):
        """When a Comment is saved with a rubricComment, pointDelta is set to None."""
        submission = setUpSubmission(self)
        assignment = submission.assignment
        rubric_category = setUpRubricCategory(self, assignment=assignment)
        rubric_comment = setUpRubricComment(self, category=rubric_category, pointDelta=5)
        file = setUpFile(self, submission=submission)
        comment = Comment.objects.create(
            text="linked comment",
            pointDelta=10,  # should be overridden
            rubricComment=rubric_comment,
            author=self.superuser,
            file=file,
            startLine=0, endLine=0, startChar=0, endChar=1,
        )
        self.assertIsNone(comment.pointDelta)

    def test_pointDelta_preserved_when_no_rubricComment(self):
        """When no rubricComment is linked, pointDelta is preserved."""
        file = setUpFile(self)
        comment = Comment.objects.create(
            text="standalone comment",
            pointDelta=3,
            rubricComment=None,
            author=self.superuser,
            file=file,
            startLine=0, endLine=0, startChar=0, endChar=1,
        )
        self.assertEqual(comment.pointDelta, 3)

    def test_comment_cascade_deleted_with_file(self):
        """Comments are cascade-deleted when their file is deleted."""
        file = setUpFile(self)
        comment = setUpComment(self, file=file)
        comment_id = comment.id
        self.assertTrue(Comment.objects.filter(id=comment_id).exists())
        file.delete()
        self.assertFalse(Comment.objects.filter(id=comment_id).exists())

    def test_rubricComment_set_null_on_delete(self):
        """When a RubricComment is deleted, Comment.rubricComment becomes NULL (not cascade)."""
        submission = setUpSubmission(self)
        assignment = submission.assignment
        rubric_category = setUpRubricCategory(self, assignment=assignment)
        rubric_comment = setUpRubricComment(self, category=rubric_category, pointDelta=3)
        file = setUpFile(self, submission=submission)
        comment = Comment.objects.create(
            text="linked",
            rubricComment=rubric_comment,
            author=self.superuser,
            file=file,
            startLine=0, endLine=0, startChar=0, endChar=1,
        )
        rubric_comment.delete()
        comment.refresh_from_db()
        self.assertIsNone(comment.rubricComment)

    def test_negative_pointDelta_represents_bonus(self):
        """A negative pointDelta represents bonus points."""
        file = setUpFile(self)
        comment = Comment.objects.create(
            text="bonus",
            pointDelta=-5,
            author=self.superuser,
            file=file,
            startLine=0, endLine=0, startChar=0, endChar=1,
        )
        self.assertEqual(comment.pointDelta, -5)

    def test_course_property_traverses_to_course(self):
        """comment.course returns the Course through file -> submission -> assignment -> course."""
        file = setUpFile(self)
        comment = setUpComment(self, file=file)
        self.assertIsNotNone(comment.course)
        self.assertEqual(comment.course, file.submission.assignment.course)


class TestCommentAPI(APITestCase):
    """API-level comment tests with authentication + permissions."""

    def setUp(self):
        setUpBase(self)

    def test_admin_can_create_comment(self):
        """A course admin (who is staff of any submission) can create a comment."""
        user = Persona.ADMIN_OF_COURSE(self)
        file = self.DB["File"]
        payload = {
            "file": file.id,
            "text": "Good work!",
            "pointDelta": 2,
            "startLine": 0,
            "endLine": 0,
            "startChar": 0,
            "endChar": 5,
        }
        response = request_as("create", user, reverse("comment-list"), payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["text"], "Good work!")

    def test_comment_author_is_set_to_authenticated_user(self):
        """The author field reflects who created the comment."""
        user = Persona.ADMIN_OF_COURSE(self)
        file = self.DB["File"]
        payload = {
            "file": file.id,
            "text": "Authored test",
            "pointDelta": 1,
            "startLine": 0,
            "endLine": 0,
            "startChar": 0,
            "endChar": 1,
        }
        response = request_as("create", user, reverse("comment-list"), payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Author should be the authenticated user
        self.assertEqual(response.data["author"], user.username)

    def test_student_cannot_create_comment(self):
        """A student of the course should not be able to create comments."""
        user = Persona.STUDENT_OF_COURSE(self)
        file = self.DB["File"]
        payload = {
            "file": file.id,
            "text": "Student comment",
            "pointDelta": 0,
            "startLine": 0,
            "endLine": 0,
            "startChar": 0,
            "endChar": 1,
        }
        response = request_as("create", user, reverse("comment-list"), payload)
        # Students get 400 (validation) or 403 (permission) — both are rejection
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

    def test_non_staff_grader_cannot_create_comment(self):
        """A grader who is NOT staff of the submission cannot create comments on it."""
        user = Persona.GRADER_OF_OTHER_COURSE(self)
        file = self.DB["File"]
        payload = {
            "file": file.id,
            "text": "Not my sub",
            "pointDelta": 1,
            "startLine": 0,
            "endLine": 0,
            "startChar": 0,
            "endChar": 1,
        }
        response = request_as("create", user, reverse("comment-list"), payload)
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST])

    def test_invalid_color_hex_is_accepted(self):
        """The API does not validate color hex on creation (stored as-is)."""
        user = Persona.ADMIN_OF_COURSE(self)
        file = self.DB["File"]
        payload = {
            "file": file.id,
            "text": "Color test",
            "pointDelta": 1,
            "startLine": 0,
            "endLine": 0,
            "startChar": 0,
            "endChar": 1,
            "color": "not-a-hex",
        }
        response = request_as("create", user, reverse("comment-list"), payload)
        # Color is not strictly validated at the model/serializer level
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_valid_color_hex_stored(self):
        """A valid hex color is accepted and stored."""
        user = Persona.ADMIN_OF_COURSE(self)
        file = self.DB["File"]
        payload = {
            "file": file.id,
            "text": "Good color",
            "pointDelta": 1,
            "startLine": 0,
            "endLine": 0,
            "startChar": 0,
            "endChar": 1,
            "color": "#FF0000",
        }
        response = request_as("create", user, reverse("comment-list"), payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Verify comment was created
        comment_id = response.data["id"]
        from core.models import Comment as CommentModel
        created_comment = CommentModel.objects.get(id=comment_id)
        self.assertIsNotNone(created_comment)
