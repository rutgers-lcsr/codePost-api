# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests for POST /courses/{id}/aiTest/ — live AI provider connection test.
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


class TestCourseAITest(APITestCase):

    def setUp(self):
        setUpBase(self)
        self.course = self.DB['Course']
        self.course.ai_use_own_settings = True
        self.course.ai_provider = 'openai'
        self.course.ai_api_key = 'sk-test'
        self.course.ai_model = 'gpt-4o-mini'
        self.course.save()
        self.endpoint = reverse('course-aiTest', args=[self.course.id])

    def test_unauthenticated_is_denied(self):
        response = self.client.post(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_and_grader_forbidden(self):
        for persona in (Persona.STUDENT_OF_COURSE(self), Persona.GRADER_OF_COURSE(self)):
            response = request_as('create', persona, self.endpoint, {})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('core.services.ai_service.AIService._dispatch_provider', new=_fake_dispatch_ok)
    def test_admin_success(self):
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('create', admin, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['provider'], 'openai')
        self.assertEqual(response.data['model'], 'gpt-4o-mini')
        self.assertEqual(response.data['response'], 'OK')
        self.assertIsNotNone(response.data['latencyMs'])
        # Test runs are recorded as 'provider_test' usage
        record = AIUsageRecord.objects.get()
        self.assertEqual(record.request_type, 'provider_test')
        self.assertEqual(record.course, self.course)
        self.assertEqual(record.organization, self.course.organization)
        self.assertEqual(record.provider, 'openai')
        self.assertEqual(record.model, 'gpt-4o-mini')
        self.assertEqual(record.status, 'success')
        self.assertEqual(record.total_tokens, 4)
        # Private token keys never leak into the API response
        self.assertNotIn('_inputTokens', response.data)

    @patch('core.services.ai_service.AIService._dispatch_provider', new=_fake_dispatch_ok)
    def test_custom_prompt_is_sent(self):
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('create', admin, self.endpoint, {'prompt': 'What is 2+2?'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['requestUserPrompt'], 'What is 2+2?')

    def test_overlong_prompt_rejected(self):
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('create', admin, self.endpoint, {'prompt': 'x' * 501})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('core.services.ai_service.AIService._dispatch_provider', new=_fake_dispatch_ok)
    def test_model_override_used_without_saving(self):
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('create', admin, self.endpoint, {'model': 'gpt-4o'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['model'], 'gpt-4o')
        self.course.refresh_from_db()
        self.assertEqual(self.course.ai_model, 'gpt-4o-mini')
        # The usage record reflects the model the test actually ran with
        self.assertEqual(AIUsageRecord.objects.get().model, 'gpt-4o')

    def test_overlong_model_rejected(self):
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('create', admin, self.endpoint, {'model': 'x' * 65})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('core.services.ai_service.AIService._dispatch_provider', new=_fake_dispatch_fail)
    def test_admin_failure_reports_error(self):
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('create', admin, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['success'])
        self.assertTrue(response.data['error'])
        self.assertIn('401', response.data['errorDetail'])
        # Failed tests are recorded too, with error status
        record = AIUsageRecord.objects.get()
        self.assertEqual(record.request_type, 'provider_test')
        self.assertEqual(record.status, 'error')

    def test_unconfigured_returns_success_false(self):
        self.course.ai_provider = ''
        self.course.save()
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('create', admin, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['success'])
        self.assertIn('No AI provider', response.data['error'])
        # No request was attempted, so nothing is recorded
        self.assertEqual(AIUsageRecord.objects.count(), 0)
