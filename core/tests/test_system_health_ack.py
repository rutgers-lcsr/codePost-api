# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
GET/PUT/DELETE /dashboard/health_ack/: the staff-wide "known problem" note the staff console's
System Health card reads. One row for everyone, superusers only.
"""
from rest_framework.test import APITestCase

from core.models import SystemHealthAcknowledgement
from core.tests.factories import OrganizationFactory, UserFactory


class SystemHealthAckTests(APITestCase):
    URL = "/dashboard/health_ack/"

    def setUp(self):
        org = OrganizationFactory(name="Org")
        self.root = UserFactory(username="root@a.edu", email="root@a.edu", organization=org, is_superuser=True, is_staff=True)
        self.other_root = UserFactory(
            username="root2@a.edu", email="root2@a.edu", organization=org, is_superuser=True, is_staff=True
        )
        self.student = UserFactory(username="s@a.edu", email="s@a.edu", organization=org)

    def test_empty_until_someone_acknowledges(self):
        self.client.force_authenticate(user=self.root)
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"signature": "", "acknowledgedBy": None, "acknowledgedAt": None})

    def test_acknowledgement_is_shared_and_names_who(self):
        self.client.force_authenticate(user=self.root)
        resp = self.client.put(self.URL, {"signature": "celery:error|cache:degraded"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["signature"], "celery:error|cache:degraded")
        self.assertEqual(resp.json()["acknowledgedBy"], "root@a.edu")
        self.assertIsNotNone(resp.json()["acknowledgedAt"])

        # Another staff member sees the same note: it is one row, not a per-browser flag.
        self.client.force_authenticate(user=self.other_root)
        resp = self.client.get(self.URL)
        self.assertEqual(resp.json()["acknowledgedBy"], "root@a.edu")
        self.assertEqual(SystemHealthAcknowledgement.objects.count(), 1)

    def test_clear(self):
        self.client.force_authenticate(user=self.root)
        self.client.put(self.URL, {"signature": "celery:error"}, format="json")
        resp = self.client.delete(self.URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"signature": "", "acknowledgedBy": None, "acknowledgedAt": None})

    def test_signature_is_required(self):
        self.client.force_authenticate(user=self.root)
        resp = self.client.put(self.URL, {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())

    def test_staff_only(self):
        self.client.force_authenticate(user=self.student)
        self.assertEqual(self.client.get(self.URL).status_code, 403)
        self.assertEqual(self.client.put(self.URL, {"signature": "x"}, format="json").status_code, 403)
