# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""GET /autograder/tasks/<id>/ returns Celery results (test and execution output).
Only the user who dispatched the task, staff of the related course and superusers may
read them; ownership comes from the task name and arguments the result backend stores."""
import json

import factory
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django_celery_results.models import TaskResult
from rest_framework.test import APITestCase

from core.tests.factories import (
    AssignmentFactory,
    CourseFactory,
    GraderFactory,
    OrganizationFactory,
    SubmissionFactory,
    UserFactory,
)

RESULT = {"output": "secret execution output"}


class TestTaskViewSetAccess(APITestCase):

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='task-org')
            cls.course = CourseFactory(name='taskcourse', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='taskcourse', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.owner = UserFactory(role='student', course='taskcourse', organization=cls.org)
            cls.classmate = UserFactory(role='student2', course='taskcourse', organization=cls.org)
            cls.course.students.add(cls.owner, cls.classmate)
            cls.assignment = AssignmentFactory(name='hw', course=cls.course)
            cls.submission = SubmissionFactory(assignment=cls.assignment)
            cls.submission.students.set([cls.owner])

            cls.other_org = OrganizationFactory(name='task-org-2')
            cls.other_course = CourseFactory(name='othertask', organization=cls.other_org)
            cls.outsider_admin = cls.other_course.courseAdmins.first()
            cls.superuser = User.objects.create_superuser(
                username='tasksuper@example.edu', email='tasksuper@example.edu', password='x')

    def _task(self, task_id, name, args_repr, kwargs_repr='{}', status='SUCCESS'):
        # Stored the way DatabaseBackend stores argsrepr/kwargsrepr under CELERY_RESULT_EXTENDED.
        TaskResult.objects.create(
            task_id=task_id, task_name=name, status=status, result=json.dumps(RESULT),
            task_args=json.dumps(args_repr), task_kwargs=json.dumps(kwargs_repr))

    def _poll(self, user, task_id):
        self.client.force_authenticate(user=user)
        return self.client.get(f'/autograder/tasks/{task_id}/')

    def test_dispatching_student_reads_own_test_run(self):
        self._task('t-own', 'autograder.tasks.run_test_task', f'({self.submission.id},)',
                   f"{{'user_id': {self.owner.id}, 'file_overrides': None}}")
        response = self._poll(self.owner, 't-own')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result'], RESULT)

    def test_dispatcher_still_reads_when_kwargs_repr_is_truncated(self):
        self._task('t-long', 'autograder.tasks.run_test_task', f'({self.submission.id},)',
                   f"{{'user_id': {self.owner.id}, 'file_overrides': {{1: '" + 'x' * 900 + "...")
        self.assertEqual(self._poll(self.owner, 't-long').status_code, 200)

    def test_other_student_cannot_read_a_test_run(self):
        self._task('t-peek', 'autograder.tasks.run_test_task', f'({self.submission.id},)',
                   f"{{'user_id': {self.owner.id}}}")
        response = self._poll(self.classmate, 't-peek')
        self.assertEqual(response.status_code, 403)
        self.assertIn('detail', response.json())
        self.assertNotIn('secret', json.dumps(response.json()))

    def test_admin_of_another_course_cannot_read(self):
        self._task('t-xcourse', 'autograder.tasks.run_test_task', f'({self.submission.id},)',
                   f"{{'user_id': {self.owner.id}}}")
        self.assertEqual(self._poll(self.outsider_admin, 't-xcourse').status_code, 403)

    def test_course_staff_and_superuser_can_read(self):
        self._task('t-staff', 'autograder.tasks.run_test_task', f'({self.submission.id},)',
                   f"{{'user_id': {self.owner.id}}}")
        for user in (self.grader, self.admin, self.superuser):
            self.assertEqual(self._poll(user, 't-staff').status_code, 200, user)

    def test_run_all_owner_is_the_positional_user(self):
        from core.models import Environment
        with factory.django.mute_signals(post_save):
            env = Environment.objects.create(assignment=self.assignment)
        self._task('t-runall', 'autograder.run.RunAll', f'({env.id}, {self.admin.id}, False)')
        self.assertEqual(self._poll(self.admin, 't-runall').status_code, 200)
        self.assertEqual(self._poll(self.classmate, 't-runall').status_code, 403)
        self.assertEqual(self._poll(self.outsider_admin, 't-runall').status_code, 403)

    def test_unrecognised_task_is_superuser_only(self):
        self._task('t-unknown', 'some.other.task', '(1,)')
        self.assertEqual(self._poll(self.owner, 't-unknown').status_code, 403)
        self.assertEqual(self._poll(self.superuser, 't-unknown').status_code, 200)

    def test_unknown_task_id_still_reads_pending(self):
        response = self._poll(self.owner, 'never-dispatched')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'PENDING', 'result': None})

    def test_task_whose_object_is_gone_is_superuser_only(self):
        self._task('t-gone', 'autograder.tasks.run_test_task', '(999999,)', "{'user_id': 424242}")
        self.assertEqual(self._poll(self.admin, 't-gone').status_code, 403)
        self.assertEqual(self._poll(self.superuser, 't-gone').status_code, 200)

    def test_run_all_without_a_stored_dispatcher_falls_back_to_course_staff(self):
        from core.models import Environment
        with factory.django.mute_signals(post_save):
            env = Environment.objects.create(assignment=self.assignment)
        self._task('t-short', 'autograder.run.RunAll', f'({env.id},)')
        self.assertEqual(self._poll(self.grader, 't-short').status_code, 200)
        self.assertEqual(self._poll(self.classmate, 't-short').status_code, 403)
