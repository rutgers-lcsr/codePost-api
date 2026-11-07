# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""GET /courses/{id}/aiModels/ and /organizations/{id}/aiModels/ report a failed live
model listing as a classified message, never the provider's raw exception text."""
from unittest.mock import AsyncMock, patch

import httpx
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona

RAW = 'connect to http://10.9.8.7:11434/api/tags failed: token=sk-leaked-secret'


def _listing_fails(exc):
    return patch('core.services.ai_service.list_provider_models', new=AsyncMock(side_effect=exc))


class TestAIModelsLiveError(APITestCase):

    def setUp(self):
        setUpBase(self)
        self.course.ai_use_own_settings = True
        self.course.ai_provider = 'openai'
        self.course.ai_api_key = 'sk-test'
        self.course.ai_model = 'gpt-4o-mini'
        self.course.save()
        self.org = self.DB['Organization']
        self.org.ai_provider = 'openai'
        self.org.ai_api_key = 'sk-org'
        self.org.save()
        self.course_url = reverse('course-aiModels', args=[self.course.id])
        self.org_url = reverse('organization-aiModels', args=[self.org.id])

    def _org_staff(self):
        user = Persona.GRADER_OF_COURSE(self)
        user.profile.isOrgStaff = True
        user.profile.organization = self.org
        user.profile.save()
        return user

    def _live_error(self, user, url):
        response = request_as('read', user, url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data['providers'][0]['liveError']

    def test_course_listing_failure_hides_the_raw_text(self):
        with _listing_fails(Exception(RAW)):
            error = self._live_error(Persona.ADMIN_OF_COURSE(self), self.course_url)
        self.assertNotIn('sk-leaked-secret', error)
        self.assertNotIn('10.9.8.7', error)
        self.assertTrue(error)

    def test_org_listing_failure_hides_the_raw_text(self):
        with _listing_fails(Exception(RAW)):
            error = self._live_error(self._org_staff(), self.org_url)
        self.assertNotIn('sk-leaked-secret', error)
        self.assertNotIn('10.9.8.7', error)
        self.assertTrue(error)

    def test_connection_failure_says_so(self):
        with _listing_fails(httpx.ConnectError(RAW)):
            error = self._live_error(Persona.ADMIN_OF_COURSE(self), self.course_url)
        self.assertEqual(error, 'Failed to connect to AI service. Please try again later.')

    def test_successful_listing_has_no_error(self):
        live = [{'id': 'gpt-x', 'name': 'GPT X'}]
        with patch('core.services.ai_service.list_provider_models', new=AsyncMock(return_value=live)):
            response = request_as('read', Persona.ADMIN_OF_COURSE(self), self.course_url)
        provider = response.data['providers'][0]
        self.assertEqual(provider['liveModels'], live)
        self.assertNotIn('liveError', provider)
