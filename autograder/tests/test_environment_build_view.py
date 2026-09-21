# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from unittest import mock

import factory
import kombu.exceptions
from django.db.models.signals import post_save
from rest_framework.test import APITestCase

from core.models import Environment
from core.tests.factories import CourseFactory


class EnvironmentBuildBrokerOutageTests(APITestCase):
    """PATCH /autograder/environments/{id}/build/ flips build_status to 'Building' before
    enqueueing; if the broker is down nothing would ever advance it, so it must fail."""

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.course = CourseFactory(name="ag-build", period="s2026", organization__name="BuildOrg")
        self.env = Environment.objects.create(assignment=self.course.assignments.first(),
                                              language='python-3.12', auto_detect=False)

    def test_broker_outage_marks_the_build_failed(self):
        self.client.force_authenticate(user=self.course.courseAdmins.first())
        with mock.patch('autograder.run.BuildEnvironment.delay',
                        side_effect=kombu.exceptions.OperationalError('Error 111 connecting to redis:6379')):
            resp = self.client.patch(f'/autograder/environments/{self.env.id}/build/', {}, format='json')

        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.data['task'], 'async_failed')
        self.env.refresh_from_db()
        self.assertEqual(self.env.build_status, 3)
        self.assertIn('Could not queue build', self.env.build_logs)
