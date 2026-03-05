# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Integration tests for the course AI settings inheritance behavior:
- Course inherits org AI config when ai_use_own_settings=False and org policy allows it
- Course uses own settings when ai_use_own_settings=True
- orgAiAvailable field reflects actual state
- Toggling ai_use_own_settings changes effective config
"""
from django.db.models.signals import post_save
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

import factory.django

from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona
from core.models import Organization, Course


class TestCourseAISettingsInheritance(APITestCase):
    """Test that the course AI settings correctly reflect org inheritance."""

    def setUp(self):
        setUpBase(self)
        self.org = self.DB['Organization']
        self.course = self.DB['Course']
        self.course_endpoint = reverse('course-aiSettings', args=[self.course.id])

    def _configure_org(self, policy='all', **kwargs):
        """Helper to set up org AI settings."""
        defaults = dict(
            ai_provider='gemini',
            ai_api_key='org-secret-key',
            ai_model='gemini-2.5-flash',
            ai_disabled=False,
            ai_course_policy=policy,
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self.org, k, v)
        self.org.save()

    # ------------------------------------------------------------------
    # orgAiAvailable reflects org state
    # ------------------------------------------------------------------

    def test_org_ai_not_available_by_default(self):
        """Without org AI configured, orgAiAvailable is False."""
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.course_endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['orgAiAvailable'])

    def test_org_ai_available_when_configured_policy_all(self):
        self._configure_org(policy='all')
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.course_endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['orgAiAvailable'])

    def test_org_ai_not_available_when_policy_none(self):
        self._configure_org(policy='none')
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.course_endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['orgAiAvailable'])

    def test_org_ai_available_when_policy_selected_and_course_enabled(self):
        self._configure_org(policy='selected')
        self.org.ai_enabled_courses.add(self.course)
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.course_endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['orgAiAvailable'])

    def test_org_ai_not_available_when_policy_selected_and_course_not_enabled(self):
        self._configure_org(policy='selected')
        # Don't add this course to the enabled list
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.course_endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['orgAiAvailable'])

    def test_org_ai_not_available_when_org_disabled(self):
        self._configure_org(policy='all', ai_disabled=True)
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.course_endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['orgAiAvailable'])

    # ------------------------------------------------------------------
    # Inheritance: aiEnabled reflects effective config
    # ------------------------------------------------------------------

    def test_course_inherits_org_ai_enabled(self):
        """Course with no own settings but org configured → aiEnabled=True."""
        self._configure_org(policy='all')
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.course_endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['aiEnabled'])
        self.assertFalse(response.data['aiUseOwnSettings'])

    def test_course_uses_own_overrides_org(self):
        """Course sets ai_use_own_settings=True and has its own key → uses own config."""
        self._configure_org(policy='all')
        admin = Persona.ADMIN_OF_COURSE(self)

        # Set course's own settings
        response = request_as('update', admin, self.course_endpoint, {
            'aiUseOwnSettings': True,
            'aiProvider': 'openai',
            'aiApiKey': 'course-own-key',
            'aiModel': 'gpt-4o',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['aiUseOwnSettings'])
        self.assertTrue(response.data['aiEnabled'])
        self.assertEqual(response.data['aiProvider'], 'openai')

    def test_toggle_use_own_settings(self):
        """Toggle ai_use_own_settings affects which config is effective."""
        self._configure_org(policy='all')
        admin = Persona.ADMIN_OF_COURSE(self)

        # First set own settings
        request_as('update', admin, self.course_endpoint, {
            'aiUseOwnSettings': True,
            'aiProvider': 'openai',
            'aiApiKey': 'own-key',
        })

        # Now switch back to org inheritance
        response = request_as('update', admin, self.course_endpoint, {
            'aiUseOwnSettings': False,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['aiUseOwnSettings'])
        # aiProvider still shows the course's stored value (openai)
        # but aiEnabled=True because effective config comes from org
        self.assertTrue(response.data['aiEnabled'])
        self.assertTrue(response.data['orgAiAvailable'])

    def test_course_without_own_config_and_no_org_ai(self):
        """Course with no settings and no org AI → aiEnabled=False."""
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.course_endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['aiEnabled'])
        self.assertFalse(response.data['aiCommentsEnabled'])

    def test_portkey_org_inheritance_without_api_key(self):
        """Portkey org with only base_url (no API key) should still allow course inheritance."""
        self._configure_org(
            policy='all',
            ai_provider='portkey',
            ai_api_key='',
            ai_base_url='http://portkey-gateway.local:8787',
            ai_model='gpt-4o',
        )
        admin = Persona.ADMIN_OF_COURSE(self)
        response = request_as('read', admin, self.course_endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['orgAiAvailable'])
        self.assertTrue(response.data['aiEnabled'])
