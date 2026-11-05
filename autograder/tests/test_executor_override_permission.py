# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Overriding a submission's code when executing it requires course admin, or a grader
on an assignment with gradersCanEditSubmissions. The async and streaming endpoints must
apply the same rule."""
import json
from unittest import mock

import factory
from django.db.models.signals import post_save
from rest_framework.test import APITestCase

from core.tests.factories import (
    AssignmentFactory,
    CourseFactory,
    GraderFactory,
    OrganizationFactory,
    SubmissionFactory,
)

ASYNC_URL = '/autograder/execute/file/async/'
STREAM_URL = '/autograder/execute/file/streaming/'


class TestExecutorOverridePermission(APITestCase):

    def setUp(self):
        with factory.django.mute_signals(post_save):
            org = OrganizationFactory(name='exec-org')
            self.course = CourseFactory(name='execc', organization=org)
            self.admin = self.course.courseAdmins.first()
            self.grader = GraderFactory(course='execc', organization=org)
            self.course.graders.add(self.grader)
            self.assignment = AssignmentFactory(name='hw', course=self.course)
            self.submission = SubmissionFactory(assignment=self.assignment)
            self.submission.grader = self.grader
            self.submission.save()
            self.file = self.submission.files.first()

    def _allow_graders(self, value):
        with factory.django.mute_signals(post_save):
            self.assignment.gradersCanEditSubmissions = value
            self.assignment.save()

    def _async(self, user):
        self.client.force_authenticate(user=user)
        with mock.patch('autograder.views.executor_async.run_file_task') as task:
            task.delay.return_value.id = 'task-1'
            response = self.client.post(
                ASYNC_URL, {'file_id': self.file.id, 'code_override': 'print(1)'}, format='json')
        return response, task.delay.called

    def _stream_denied(self, user):
        self.client.force_authenticate(user=user)
        redis = mock.MagicMock()
        redis.pubsub.return_value.get_message.return_value = {
            'type': 'message', 'data': json.dumps({'event': '_done', 'data': None})}
        with mock.patch('autograder.tasks._get_redis_client', return_value=redis), \
                mock.patch('autograder.tasks.run_file_streaming_task'):
            response = self.client.post(
                STREAM_URL, {'file_id': self.file.id, 'code_override': 'print(1)'}, format='json')
            self.assertEqual(response.status_code, 200)
            body = b''.join(response.streaming_content).decode()
        return 'Permission denied' in body

    def test_async_grader_denied_without_flag(self):
        response, dispatched = self._async(self.grader)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(dispatched)

    def test_async_grader_allowed_with_flag(self):
        self._allow_graders(True)
        response, dispatched = self._async(self.grader)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(dispatched)

    def test_async_admin_allowed_without_flag(self):
        response, dispatched = self._async(self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(dispatched)

    def test_streaming_grader_denied_without_flag(self):
        self.assertTrue(self._stream_denied(self.grader))

    def test_streaming_grader_allowed_with_flag(self):
        self._allow_graders(True)
        self.assertFalse(self._stream_denied(self.grader))

    def test_streaming_admin_allowed_without_flag(self):
        self.assertFalse(self._stream_denied(self.admin))
