# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Course.allowGradersToEditRubric: 'graders will be allowed to add and update unlinked
rubric comments' (the model help text, and the toggle in the organization UI). Linked
means a grading Comment already uses the rubric comment."""
import factory
from django.db.models.signals import post_save
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


class TestGradersEditUnlinkedRubricComments(APITestCase):

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.org = OrganizationFactory(name='rc-org')
            self.course = CourseFactory(name='rc', organization=self.org, allowGradersToEditRubric=True)
            self.grader = GraderFactory(course='rc', organization=self.org)
            self.course.graders.add(self.grader)
            self.assignment = AssignmentFactory(name='hw', course=self.course)
            self.category = RubricCategory.objects.create(
                assignment=self.assignment, name='cat', pointLimit=5, sortKey=1)
            self.unlinked = RubricComment.objects.create(category=self.category, text='free', pointDelta=1)
            self.linked = RubricComment.objects.create(category=self.category, text='used', pointDelta=1)
            student = StudentFactory(course='rc', organization=self.org)
            self.course.students.add(student)
            submission = SubmissionFactory(assignment=self.assignment)
            submission.students.add(student)
            file = submission.files.first()
            Comment.objects.create(
                text='c', pointDelta=1, author=self.grader, file=file, rubricComment=self.linked,
                startLine=0, endLine=0, startChar=0, endChar=1)
        self.client = APIClient()
        self.client.force_authenticate(user=self.grader)

    def _flag(self, value):
        with factory.django.mute_signals(post_save):
            self.course.allowGradersToEditRubric = value
            self.course.save()

    def _create(self):
        with factory.django.mute_signals(post_save):
            return self.client.post('/rubricComments/', {
                'category': self.category.id, 'text': 'new', 'pointDelta': 1}, format='json')

    def test_flagged_grader_can_add_rubric_comment(self):
        self.assertEqual(self._create().status_code, 201)

    def test_unflagged_grader_cannot_add_rubric_comment(self):
        self._flag(False)
        self.assertEqual(self._create().status_code, 403)

    def test_flagged_grader_can_update_unlinked_rubric_comment(self):
        response = self.client.patch(f'/rubricComments/{self.unlinked.id}/', {'text': 'edited'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.unlinked.refresh_from_db()
        self.assertEqual(self.unlinked.text, 'edited')

    def test_flagged_grader_cannot_update_linked_rubric_comment(self):
        response = self.client.patch(f'/rubricComments/{self.linked.id}/', {'text': 'edited'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.linked.refresh_from_db()
        self.assertEqual(self.linked.text, 'used')

    def test_unflagged_grader_cannot_update_unlinked_rubric_comment(self):
        self._flag(False)
        response = self.client.patch(f'/rubricComments/{self.unlinked.id}/', {'text': 'edited'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_flagged_grader_cannot_delete_rubric_comment(self):
        response = self.client.delete(f'/rubricComments/{self.unlinked.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(RubricComment.objects.filter(id=self.unlinked.id).exists())

    def test_flagged_grader_cannot_write_categories(self):
        # The setting's spec covers rubric comments only.
        response = self.client.post('/rubricCategories/', {
            'assignment': self.assignment.id, 'name': 'x', 'pointLimit': 5, 'sortKey': 2}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_archived_course_blocks_flagged_grader(self):
        with factory.django.mute_signals(post_save):
            self.course.archived = True
            self.course.save()
        self.assertGreaterEqual(self._create().status_code, 400)
        response = self.client.patch(f'/rubricComments/{self.unlinked.id}/', {'text': 'edited'}, format='json')
        self.assertGreaterEqual(response.status_code, 400)
        self.unlinked.refresh_from_db()
        self.assertEqual(self.unlinked.text, 'free')

    def test_flagged_grader_of_another_course_has_no_access(self):
        with factory.django.mute_signals(post_save):
            other = CourseFactory(name='rc2', period='Spring', organization=self.org, allowGradersToEditRubric=True)
            outsider = GraderFactory(course='rc2', organization=self.org)
            other.graders.add(outsider)
        client = APIClient()
        client.force_authenticate(user=outsider)
        response = client.patch(f'/rubricComments/{self.unlinked.id}/', {'text': 'edited'}, format='json')
        self.assertIn(response.status_code, (403, 404))
