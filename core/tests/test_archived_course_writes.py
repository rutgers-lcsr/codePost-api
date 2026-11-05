# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import factory
from django.db.models.signals import post_save
from rest_framework.test import APITestCase

from core.models import Comment, Course, RubricCategory, RubricComment, Submission
from core.tests.factories import CourseFactory


class ArchivedCourseWritesTest(APITestCase):
  """An archived course is read-only: create and delete are refused like edits are."""

  def setUp(self):
    self.course = CourseFactory()
    self.admin = self.course.courseAdmins.first()
    self.assignment = self.course.assignments.first()
    self.sub = self.assignment.submissions.first()
    self.file = self.sub.files.first()
    self.category = self.assignment.rubricCategories.first()
    self.rubricComment = self.category.rubricComments.first()
    self.comment = self.file.comments.first()
    Course.objects.filter(pk=self.course.pk).update(archived=True)
    self.client.force_authenticate(user=self.admin)

  def assertRefused(self, response):
    self.assertEqual(response.status_code, 403, response.content)
    self.assertIn('archived', response.json()['detail'].lower())

  def test_post_comment_refused(self):
    before = Comment.objects.count()
    r = self.client.post('/comments/', {'text': 'new', 'pointDelta': 1, 'startLine': 0, 'endLine': 0,
                                        'startChar': 0, 'endChar': 1, 'file': self.file.id}, format='json')
    self.assertRefused(r)
    self.assertEqual(Comment.objects.count(), before)

  def test_post_rubric_category_refused(self):
    before = RubricCategory.objects.count()
    r = self.client.post('/rubricCategories/', {'assignment': self.assignment.id, 'name': 'new'}, format='json')
    self.assertRefused(r)
    self.assertEqual(RubricCategory.objects.count(), before)

  def test_post_rubric_comment_refused(self):
    before = RubricComment.objects.count()
    r = self.client.post('/rubricComments/', {'category': self.category.id, 'text': 'new', 'pointDelta': 1}, format='json')
    self.assertRefused(r)
    self.assertEqual(RubricComment.objects.count(), before)

  def test_delete_comment_refused(self):
    self.assertRefused(self.client.delete(f'/comments/{self.comment.id}/'))
    self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())

  def test_delete_rubric_comment_refused(self):
    self.assertRefused(self.client.delete(f'/rubricComments/{self.rubricComment.id}/'))
    self.assertTrue(RubricComment.objects.filter(pk=self.rubricComment.pk).exists())

  def test_delete_submission_refused(self):
    self.assertRefused(self.client.delete(f'/submissions/{self.sub.id}/'))
    self.assertTrue(Submission.objects.filter(pk=self.sub.pk).exists())

  def test_reads_still_work(self):
    self.assertEqual(self.client.get(f'/submissions/{self.sub.id}/').status_code, 200)
    self.assertEqual(self.client.get(f'/comments/{self.comment.id}/').status_code, 200)

  def test_course_can_be_unarchived(self):
    r = self.client.patch(f'/courses/{self.course.id}/', {'archived': False}, format='json')
    self.assertEqual(r.status_code, 200, r.content)
    self.course.refresh_from_db()
    self.assertFalse(self.course.archived)
    self.assertEqual(self.client.delete(f'/comments/{self.comment.id}/').status_code, 204)

  def test_unarchived_course_unaffected(self):
    Course.objects.filter(pk=self.course.pk).update(archived=False)
    self.assertEqual(self.client.delete(f'/comments/{self.comment.id}/').status_code, 204)

  def test_assignment_can_be_cloned_out_of_archived_course(self):
    # Semester rollover: a POST action that only reads the archived object is not an edit.
    with factory.django.mute_signals(post_save):
      target = CourseFactory(name='cos226', period='s2020', organization=self.course.organization)
    target.courseAdmins.add(self.admin)
    r = self.client.post(f'/assignments/{self.assignment.id}/clone/', {'course': target.id}, format='json')
    self.assertEqual(r.status_code, 200, r.content)
    self.assertTrue(target.assignments.filter(name=self.assignment.name).exists())
