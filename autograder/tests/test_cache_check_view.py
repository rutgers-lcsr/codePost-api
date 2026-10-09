# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.contrib.auth.models import User
from rest_framework.test import APITestCase


class CacheCheckMissingFileTests(APITestCase):
    """File.get_file_obj raises DoesNotExist for an unknown id; the view's 404 branch
    was unreachable and the request 500'd."""

    def test_unknown_file_id_is_404(self):
        user = User.objects.create(username="cache@example.edu", email="cache@example.edu")
        self.client.force_authenticate(user=user)
        resp = self.client.get('/autograder/execute/file/cache/check/', {'file_id': 999999})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()['error'], 'File not found')
