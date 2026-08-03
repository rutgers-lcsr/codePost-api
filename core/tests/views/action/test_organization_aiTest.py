# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests for POST /organizations/{id}/aiTest/ — live AI provider connection test.
"""
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import AIUsageRecord
from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona


async def _fake_dispatch_ok(self, system_prompt, user_prompt):
    return ('OK', 3, 1, 4, 0)


async def _fake_dispatch_fail(self, system_prompt, user_prompt):
    raise Exception('401 unauthorized: invalid api key')


class TestOrganizationAITest(APITestCase):

    def setUp(self):
        setUpBase(self)
        self.org = self.DB['Organization']
        self.org.ai_provider = 'openai'
        self.org.ai_api_key = 'sk-org'
        self.org.ai_model = 'gpt-4o-mini'
        self.org.save()
        self.endpoint = reverse('organization-aiTest', args=[self.org.id])

    def _org_staff(self):
        user = Persona.GRADER_OF_COURSE(self)
        user.profile.isOrgStaff = True
        user.profile.organization = self.org
        user.profile.save()
        return user

    def test_unauthenticated_is_denied(self):
        response = self.client.post(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_org_staff_is_forbidden(self):
        grader = Persona.GRADER_OF_COURSE(self)
        response = request_as('create', grader, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('core.services.ai_service.AIService._dispatch_provider', new=_fake_dispatch_ok)
    def test_superuser_success(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su_aitest@test.edu', 'su_aitest@test.edu', 'pass')
        response = request_as('create', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['provider'], 'openai')
        self.assertEqual(response.data['model'], 'gpt-4o-mini')
        self.assertEqual(response.data['response'], 'OK')
        self.assertIsNotNone(response.data['latencyMs'])
        self.assertEqual(AIUsageRecord.objects.count(), 0)

    @patch('core.services.ai_service.AIService._dispatch_provider', new=_fake_dispatch_ok)
    def test_org_staff_success(self):
        """Org staff (non-superuser) can test — regression for get_permissions."""
        staff = self._org_staff()
        response = request_as('create', staff, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    @patch('core.services.ai_service.AIService._dispatch_provider', new=_fake_dispatch_fail)
    def test_failure_reports_error(self):
        staff = self._org_staff()
        response = request_as('create', staff, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['success'])
        self.assertTrue(response.data['error'])
        self.assertIn('401', response.data['errorDetail'])
        self.assertEqual(AIUsageRecord.objects.count(), 0)

    def test_unconfigured_returns_success_false(self):
        self.org.ai_provider = ''
        self.org.save()
        staff = self._org_staff()
        response = request_as('create', staff, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['success'])
        self.assertIn('No AI provider', response.data['error'])
