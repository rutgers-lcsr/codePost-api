# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase, APIClient


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
