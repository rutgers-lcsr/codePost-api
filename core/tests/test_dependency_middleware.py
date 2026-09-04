# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""DependencyUnavailableMiddleware: DB/broker outages become a JSON 503, nothing else changes."""
import kombu.exceptions
import redis.exceptions
from django.db.utils import InterfaceError, OperationalError
from django.test import TestCase, override_settings
from django.urls import path

_ERRORS = {
    'db': OperationalError('MySQL server has gone away'),
    'interface': InterfaceError('connection already closed'),
    'broker': kombu.exceptions.OperationalError('Error 111 connecting to redis:6379'),
    'redis-connection': redis.exceptions.ConnectionError('Connection refused'),
    'redis-timeout': redis.exceptions.TimeoutError('Timeout reading from socket'),
    'other': RuntimeError('unrelated bug'),
}


def _boom(request, kind):
    raise _ERRORS[kind]


urlpatterns = [path('boom/<str:kind>/', _boom)]


@override_settings(ROOT_URLCONF='core.tests.test_dependency_middleware')
class DependencyUnavailableMiddlewareTests(TestCase):

    def test_dependency_errors_become_503(self):
        for kind in ('db', 'interface', 'broker', 'redis-connection', 'redis-timeout'):
            with self.subTest(kind=kind):
                response = self.client.get(f'/boom/{kind}/')
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response['Retry-After'], '10')
                self.assertEqual(response['Content-Type'], 'application/json')
                self.assertIn('temporarily unavailable', response.json()['detail'])

    def test_unrelated_errors_still_propagate(self):
        with self.assertRaises(RuntimeError):
            self.client.get('/boom/other/')
