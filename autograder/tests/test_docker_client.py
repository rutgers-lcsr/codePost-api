# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from unittest import mock

from django.test import SimpleTestCase

from autograder.services.executors.base import Executor


class DockerClientAcquisitionTests(SimpleTestCase):
    """A Docker daemon restart must not leave the executor reusing a dead client forever."""

    def setUp(self):
        self._saved = Executor._docker_client

    def tearDown(self):
        Executor._docker_client = self._saved

    @mock.patch('autograder.services.executors.base.DOCKER_AVAILABLE', True)
    def test_dead_client_is_dropped(self):
        dead = mock.Mock()
        dead.ping.side_effect = Exception('Cannot connect to the Docker daemon')
        Executor._docker_client = dead

        self.assertIsNone(Executor._get_docker_client())
        self.assertIsNone(Executor._docker_client)  # rebuilt on the next acquisition

    @mock.patch('autograder.services.executors.base.DOCKER_AVAILABLE', True)
    def test_live_client_is_pinged_and_reused(self):
        live = mock.Mock()
        Executor._docker_client = live

        self.assertIs(Executor._get_docker_client(), live)
        live.ping.assert_called_once()
