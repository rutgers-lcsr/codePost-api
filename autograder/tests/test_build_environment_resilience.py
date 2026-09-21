# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from unittest import mock

from django.test import TestCase

from autograder.run import BuildEnvironment
from core.models import Environment
from core.tests.factories import AssignmentFactory


class BuildEnvironmentDockerOutageTests(TestCase):
    """The build view flips build_status to 'Building' before enqueueing; if the worker
    cannot even create a Docker client the task must fail the build, not strand it."""

    def test_marks_build_failed_when_docker_daemon_is_unreachable(self):
        env = Environment.objects.create(assignment=AssignmentFactory(), language='python-3.12',
                                         auto_detect=False, build_status=1, build_logs='Queued for build...\n')

        with mock.patch('autograder.run.Builder', side_effect=Exception('Cannot connect to the Docker daemon')):
            with self.assertRaises(Exception):
                BuildEnvironment(env.id)

        env.refresh_from_db()
        self.assertEqual(env.build_status, 3)
        self.assertIn('cannot reach its Docker daemon', env.build_logs)
