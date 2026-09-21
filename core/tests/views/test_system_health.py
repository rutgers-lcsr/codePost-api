# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from unittest import mock

import kombu.exceptions
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from core.views.system import SystemHealthView


class TestSystemHealthEndpoint(APITestCase):
    """Tests for GET /system/health/"""

    endpoint = '/system/health/'

    def test_unauthenticated_returns_401(self):
        response = APIClient().get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_staff_returns_403(self):
        user = User.objects.create_user('plain@test.edu', 'plain@test.edu', 'pass')
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_gets_database_connection_metrics(self):
        staff = User.objects.create_user('staff@test.edu', 'staff@test.edu', 'pass', is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff)
        response = client.get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        db = response.data['database']
        self.assertEqual(db['status'], 'ok')
        # Connection-pool metrics are MySQL-only; the test DB is SQLite, so the
        # fields must be present but None.
        self.assertIn('connections_current', db)
        self.assertIn('connections_max_used', db)
        self.assertIn('connections_limit', db)
        self.assertIsNone(db['connections_current'])
        self.assertIsNone(db['connections_max_used'])
        self.assertIsNone(db['connections_limit'])

    def test_dependency_outage_inside_a_drf_view_is_a_503(self):
        """DependencyUnavailableMiddleware also covers DRF views (DRF re-raises non-APIExceptions)."""
        staff = User.objects.create_user('staff2@test.edu', 'staff2@test.edu', 'pass', is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff)
        with mock.patch.object(SystemHealthView, 'get', side_effect=kombu.exceptions.OperationalError('broker down')):
            response = client.get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response['Retry-After'], '10')
        self.assertIn('temporarily unavailable', response.json()['detail'])


class TestReadinessEndpoint(APITestCase):
    """GET /health-check/ready/ — unauthenticated readiness probe (DB + broker)."""

    endpoint = '/health-check/ready/'

    @mock.patch('core.views.system._check_redis', return_value='ok')
    def test_ok_when_dependencies_answer(self, _redis):
        response = APIClient().get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {'status': 'ok', 'database': 'ok', 'redis': 'ok'})

    @mock.patch('core.views.system._check_redis', return_value='ok')
    @mock.patch('core.views.system._check_database', return_value={'status': 'error', 'detail': 'secret host'})
    def test_503_when_database_down(self, _db, _redis):
        response = APIClient().get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response['Retry-After'], '10')
        self.assertEqual(response.json(), {'status': 'unavailable', 'database': 'error', 'redis': 'ok'})
        self.assertNotIn('secret host', response.content.decode())

    @mock.patch('core.views.system._check_redis', return_value='error')
    def test_503_when_redis_down(self, _redis):
        response = APIClient().get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()['redis'], 'error')

    def test_liveness_stays_unconditional(self):
        # /health-check/ is what compose + autoheal watch; it must not depend on anything.
        with mock.patch('core.views.system._check_database', return_value={'status': 'error'}):
            self.assertEqual(APIClient().get('/health-check/').status_code, status.HTTP_200_OK)
