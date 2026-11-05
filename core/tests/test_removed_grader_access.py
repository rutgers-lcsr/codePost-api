# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.test import APITestCase

from core.tests.factories import CourseFactory


class RemovedGraderAccessTest(APITestCase):
  """Staff access follows current course membership, not the stale submission.grader."""

  def setUp(self):
    self.course = CourseFactory()
    self.grader = self.course.graders.exclude(superGrader_courses=self.course).first()
    self.admin = self.course.courseAdmins.first()
    self.sub = self.course.assignments.first().submissions.first()
    self.sub.grader = self.grader
    self.sub.save()

  def _remove_from_roster(self):
    self.client.force_authenticate(user=self.admin)
    r = self.client.patch(f'/courses/{self.course.id}/removeFromRoster/', {'graders': [self.grader.username]}, format='json')
    self.assertEqual(r.status_code, 200, r.content)
    self.assertFalse(self.course.graders.filter(id=self.grader.id).exists())

  def test_assigned_grader_has_access_while_on_roster(self):
    self.client.force_authenticate(user=self.grader)
    self.assertEqual(self.client.get(f'/submissions/{self.sub.id}/').status_code, 200)

  def test_removed_grader_loses_access(self):
    self._remove_from_roster()
    self.client.force_authenticate(user=self.grader)
    self.assertEqual(self.client.get(f'/submissions/{self.sub.id}/').status_code, 403)
    r = self.client.patch(f'/submissions/{self.sub.id}/', {'isFinalized': True}, format='json')
    self.assertEqual(r.status_code, 403)
    file = self.sub.files.first()
    self.assertEqual(self.client.get(f'/files/{file.id}/').status_code, 403)
