# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import json
from unittest import mock

import factory
from django.db.models.signals import post_save
from rest_framework.test import APITestCase

from core.models import Environment, TestCase as TestCaseModel
from core.tests.factories import CourseFactory, TestCategoryFactory


class EnvironmentEjectTests(APITestCase):
    """GET /autograder/environments/{id}/eject/ used to 500 whenever any test existed:
    it read fields TestCase does not have."""

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.course = CourseFactory(name="ag-eject", period="s2026", organization__name="EjectOrg")
            self.assignment = self.course.assignments.first()
            category = TestCategoryFactory(assignment=self.assignment, targetFileName="main.py")
            self.test_case = TestCaseModel.objects.create(
                testCategory=category, description="prints hello", type="io", text="hello", pointsPass=2)
        self.env = Environment.objects.create(assignment=self.assignment,
                                              language='python-3.12', auto_detect=False)

    def test_eject_lists_the_assignment_tests(self):
        self.client.force_authenticate(user=self.course.courseAdmins.first())
        resp = self.client.get(f'/autograder/environments/{self.env.id}/eject/')

        self.assertEqual(resp.status_code, 200, resp.content)
        tests = json.loads(resp.data['testsJson'])
        self.assertEqual([t['id'] for t in tests], [self.test_case.id])
        self.assertEqual(tests[0]['description'], 'prints hello')
        self.assertEqual(tests[0]['type'], 'io')
        self.assertEqual(tests[0]['pointsPass'], 2.0)
        self.assertEqual(tests[0]['fileName'], 'main.py')
        self.assertTrue(resp.data['dockerfile'])
        self.assertIn('codePost Debug Kit', resp.data['runTestsPy'])


class EnvironmentRunTests(APITestCase):

    def test_run_on_missing_environment_is_404(self):
        with factory.django.mute_signals(post_save):
            course = CourseFactory(name="ag-run", period="s2026", organization__name="RunOrg")
        self.client.force_authenticate(user=course.courseAdmins.first())
        resp = self.client.patch('/autograder/environments/999999/run/', {}, format='json')
        self.assertEqual(resp.status_code, 404)


class EnvironmentRunFilesOverrideTests(APITestCase):
    """The 'files' override maps file id -> content. A JSON array used to be accepted with a 200
    and a task id, then fail inside the task with "'list' object has no attribute 'items'"."""

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.course = CourseFactory(name="ag-files", period="s2026", organization__name="FilesOrg")
            self.assignment = self.course.assignments.first()
            self.submission = self.assignment.submissions.first()
        self.env = Environment.objects.create(assignment=self.assignment,
                                              language='python-3.12', auto_detect=False)
        self.client.force_authenticate(user=self.course.courseAdmins.first())

    def _run(self, files):
        return self.client.patch(f'/autograder/environments/{self.env.id}/run/',
                                 {'submission': self.submission.id, 'files': files}, format='json')

    def test_array_override_is_a_400_not_a_silent_task_failure(self):
        resp = self._run([{'id': 1, 'content': 'x'}])

        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('files', resp.data)

    def test_object_override_is_accepted(self):
        with mock.patch('autograder.views.environment.run_test_task.delay') as delay:
            delay.return_value.task_id = 'abc'
            resp = self._run({'1': 'x = 1'})

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(delay.call_args.kwargs['file_overrides'], {'1': 'x = 1'})
