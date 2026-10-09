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
        """The broker error propagates so DependencyUnavailableMiddleware answers a JSON 503
        (not a 500 carrying the raw redis text) — after the build has been marked failed."""
        self.client.force_authenticate(user=self.course.courseAdmins.first())
        with mock.patch('autograder.run.BuildEnvironment.delay',
                        side_effect=kombu.exceptions.OperationalError('Error 111 connecting to redis:6379')):
            resp = self.client.patch(f'/autograder/environments/{self.env.id}/build/', {}, format='json')

        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp['Retry-After'], '10')
        self.assertIn('temporarily unavailable', resp.json()['detail'])
        self.assertNotIn('redis:6379', resp.content.decode())
        self.env.refresh_from_db()
        self.assertEqual(self.env.build_status, 3)
        self.assertIn('Could not queue build', self.env.build_logs)

    def test_unexpected_dispatch_error_is_a_generic_500(self):
        self.client.force_authenticate(user=self.course.courseAdmins.first())
        with mock.patch('autograder.run.BuildEnvironment.delay',
                        side_effect=RuntimeError('internal detail that must not leak')):
            resp = self.client.patch(f'/autograder/environments/{self.env.id}/build/', {}, format='json')

        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        self.assertEqual(body['error'], 'async_failed')
        self.assertEqual(body['detail'], 'Could not queue the build.')
        self.assertNotIn('must not leak', resp.content.decode())
        self.env.refresh_from_db()
        self.assertEqual(self.env.build_status, 3)
