# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""RubricComment.isApplied: true once any grading Comment uses the rubric comment."""
import factory
from django.db import connection
from django.db.models.signals import post_save
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase, APIClient

from core.models import Comment, RubricCategory, RubricComment
from core.tests.factories import (
    AssignmentFactory,
    CourseFactory,
    GraderFactory,
    OrganizationFactory,
    StudentFactory,
    SubmissionFactory,
)


class TestRubricCommentIsApplied(APITestCase):

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.org = OrganizationFactory(name='applied-org')
            self.course = CourseFactory(name='applied', organization=self.org)
            self.admin = self.course.courseAdmins.first()
            self.grader = GraderFactory(course='applied', organization=self.org)
            self.course.graders.add(self.grader)
            self.assignment = AssignmentFactory(name='hw', course=self.course)
            self.category = RubricCategory.objects.create(
                assignment=self.assignment, name='cat', pointLimit=50, sortKey=1)
            student = StudentFactory(course='applied', organization=self.org)
            self.course.students.add(student)
            submission = SubmissionFactory(assignment=self.assignment)
            submission.students.add(student)
            self.file = submission.files.first()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _make(self, applied):
        with factory.django.mute_signals(post_save):
            rc = RubricComment.objects.create(category=self.category, text='t', pointDelta=1)
            if applied:
                Comment.objects.create(
                    text='c', pointDelta=1, author=self.grader, file=self.file, rubricComment=rc,
                    startLine=0, endLine=0, startChar=0, endChar=1)
        return rc

    def _rubric(self):
        response = self.client.get(f'/assignments/{self.assignment.id}/rubric/')
        self.assertEqual(response.status_code, 200)
        return {c['id']: c['isApplied'] for c in response.data['rubricComments']}

    def test_rubric_listing_reports_applied_per_comment(self):
        applied, free = self._make(True), self._make(False)
        listed = self._rubric()
        self.assertTrue(listed[applied.id])
        self.assertFalse(listed[free.id])

    def test_detail_reports_applied(self):
        applied, free = self._make(True), self._make(False)
        self.assertTrue(self.client.get(f'/rubricComments/{applied.id}/').data['isApplied'])
        self.assertFalse(self.client.get(f'/rubricComments/{free.id}/').data['isApplied'])

    def test_listing_query_count_does_not_grow_per_comment(self):
        self._make(True)
        with CaptureQueriesContext(connection) as few:
            self._rubric()
        for _ in range(5):
            self._make(True)
            self._make(False)
        with CaptureQueriesContext(connection) as many:
            self._rubric()
        self.assertLessEqual(len(many), len(few))

    def test_nested_in_comment_serializer_is_applied_without_extra_query(self):
        from core.serializers.comment import CommentWithRubricSerializer
        rc = self._make(True)
        comment = Comment.objects.select_related('rubricComment').get(rubricComment=rc)
        with CaptureQueriesContext(connection) as ctx:
            data = CommentWithRubricSerializer(comment).data
        self.assertTrue(data['rubricComment']['isApplied'])
        self.assertFalse([q for q in ctx.captured_queries if 'rubricComment_id' in q['sql'] and 'core_rubriccomment' not in q['sql'].split('FROM')[1].split('WHERE')[0]])
