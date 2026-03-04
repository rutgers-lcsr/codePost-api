# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.tests.views.personas import Persona

from core.tests.utils import request_as, setUpBase

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Course


class TestPermissions_Course_aiSettings(APITestCase):

  def setUp(self):
    setUpBase(self)
    self.endpoint = reverse("course-aiSettings", args=[self.DB['Course'].id])

  def test_get_permissions(self):
    student = Persona.STUDENT_OF_COURSE(self)
    grader = Persona.GRADER_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)

    response = request_as('read', student, self.endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    response = request_as('read', grader, self.endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    response = request_as('read', admin, self.endpoint, {})
    self.assertEqual(response.status_code, status.HTTP_200_OK)

  def test_patch_requires_admin(self):
    grader = Persona.GRADER_OF_COURSE(self)

    response = request_as('update', grader, self.endpoint, {'aiProvider': 'openai'})
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_get_and_patch_use_camel_case_fields(self):
    admin = Persona.ADMIN_OF_COURSE(self)

    patch_payload = {
      'aiProvider': 'openai',
      'aiApiKey': 'secret-test-key',
      'aiBaseUrl': 'https://api.openai.com/v1',
      'aiModel': 'gpt-4o-mini',
      'aiDisabled': False,
      'aiCommentsDisabled': False,
    }

    patch_response = request_as('update', admin, self.endpoint, patch_payload)
    self.assertEqual(patch_response.status_code, status.HTTP_200_OK)

    # write_only: key is accepted but not exposed in response
    self.assertNotIn('aiApiKey', patch_response.data)

    expected_keys = {
      'id',
      'aiProvider',
      'aiBaseUrl',
      'aiModel',
      'aiDisabled',
      'aiCommentsDisabled',
      'aiEnabled',
      'aiCommentsEnabled',
      'aiUseOwnSettings',
      'orgAiAvailable',
    }
    self.assertEqual(set(patch_response.data.keys()), expected_keys)
    self.assertEqual(patch_response.data['aiProvider'], 'openai')
    self.assertEqual(patch_response.data['aiBaseUrl'], 'https://api.openai.com/v1')
    self.assertEqual(patch_response.data['aiModel'], 'gpt-4o-mini')
    self.assertFalse(patch_response.data['aiDisabled'])
    self.assertFalse(patch_response.data['aiCommentsDisabled'])
    self.assertTrue(patch_response.data['aiEnabled'])
    self.assertTrue(patch_response.data['aiCommentsEnabled'])

    course = Course.objects.get(id=self.DB['Course'].id)
    self.assertEqual(course.ai_provider, 'openai')
    self.assertEqual(course.ai_base_url, 'https://api.openai.com/v1')
    self.assertEqual(course.ai_model, 'gpt-4o-mini')
    self.assertEqual(course.ai_api_key, 'secret-test-key')
    self.assertFalse(course.ai_disabled)
    self.assertFalse(course.ai_comments_disabled)

    get_response = request_as('read', admin, self.endpoint, {})
    self.assertEqual(get_response.status_code, status.HTTP_200_OK)
    self.assertEqual(set(get_response.data.keys()), expected_keys)
    self.assertNotIn('aiApiKey', get_response.data)
    self.assertTrue(get_response.data['aiEnabled'])
    self.assertTrue(get_response.data['aiCommentsEnabled'])

    # Disable only AI comments and ensure global AI remains enabled
    disable_comments_response = request_as('update', admin, self.endpoint, {'aiCommentsDisabled': True})
    self.assertEqual(disable_comments_response.status_code, status.HTTP_200_OK)
    self.assertTrue(disable_comments_response.data['aiEnabled'])
    self.assertFalse(disable_comments_response.data['aiCommentsEnabled'])

    # Disable AI and ensure aiEnabled flips false
    disable_response = request_as('update', admin, self.endpoint, {'aiDisabled': True})
    self.assertEqual(disable_response.status_code, status.HTTP_200_OK)
    self.assertFalse(disable_response.data['aiEnabled'])
    self.assertFalse(disable_response.data['aiCommentsEnabled'])
