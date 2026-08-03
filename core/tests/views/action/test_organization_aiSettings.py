# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests for Organization AI Settings endpoints:
- GET /organizations/{id}/aiSettings/
- PATCH /organizations/{id}/aiSettings/
- Permissions (org staff, superuser, others)
- Course policy & enabled courses management
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona


class TestOrganizationAISettings(APITestCase):

    def setUp(self):
        setUpBase(self)
        self.org = self.DB['Organization']
        self.endpoint = reverse('organization-aiSettings', args=[self.org.id])

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def test_unauthenticated_is_denied(self):
        """Anonymous user gets 401."""
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_org_staff_is_forbidden(self):
        """A regular grader cannot read org AI settings."""
        grader = Persona.GRADER_OF_COURSE(self)
        response = request_as('read', grader, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_can_read(self):
        """Superuser can always read org AI settings."""
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su@test.edu', 'su@test.edu', 'pass')
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_superuser_can_patch(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su2@test.edu', 'su2@test.edu', 'pass')
        response = request_as('update', su, self.endpoint, {'aiProvider': 'gemini'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # GET response shape
    # ------------------------------------------------------------------

    def test_get_returns_expected_fields(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su3@test.edu', 'su3@test.edu', 'pass')
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        expected_keys = {
            'id',
            'aiProvider',
            'aiBaseUrl',
            'aiModel',
            'aiDisabled',
            'aiCommentsDisabled',
            'aiCoursePolicy',
            'aiEnabledCourseIds',
            'aiTokenRates',
            'aiFeatureConfig',
            'aiFeatureModels',
            'aiFeatures',
            'aiEnabled',
            'aiCommentsEnabled',
            'hasApiKey',
            'apiKeyHint',
            'defaultTokenRates',
        }
        self.assertEqual(set(response.data.keys()), expected_keys)
        # API key should never be in the GET response
        self.assertNotIn('aiApiKey', response.data)

    # ------------------------------------------------------------------
    # PATCH — setting provider, key, model
    # ------------------------------------------------------------------

    def test_patch_sets_ai_config(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su4@test.edu', 'su4@test.edu', 'pass')

        payload = {
            'aiProvider': 'openai',
            'aiApiKey': 'org-secret-key-123',
            'aiModel': 'gpt-4o-mini',
            'aiBaseUrl': 'https://api.openai.com/v1',
        }
        response = request_as('update', su, self.endpoint, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Read back from DB
        self.org.refresh_from_db()
        self.assertEqual(self.org.ai_provider, 'openai')
        self.assertEqual(self.org.ai_api_key, 'org-secret-key-123')
        self.assertEqual(self.org.ai_model, 'gpt-4o-mini')

        # Response says aiEnabled=True
        self.assertTrue(response.data['aiEnabled'])
        self.assertTrue(response.data['aiCommentsEnabled'])
        self.assertTrue(response.data['hasApiKey'])

    def test_hasApiKey_false_when_no_key(self):
        """hasApiKey should be False when no API key has been saved."""
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su_nokey@test.edu', 'su_nokey@test.edu', 'pass')
        # Set provider but no key
        request_as('update', su, self.endpoint, {'aiProvider': 'gemini'})
        response = request_as('read', su, self.endpoint, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['hasApiKey'])

    def test_patch_portkey_provider(self):
        """Portkey should be a valid provider choice."""
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su_portkey@test.edu', 'su_portkey@test.edu', 'pass')
        payload = {
            'aiProvider': 'portkey',
            'aiApiKey': 'pk-test-key',
            'aiBaseUrl': 'https://portkey.rutgers.edu/v1',
            'aiModel': 'llama-3.1-70b',
        }
        response = request_as('update', su, self.endpoint, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.ai_provider, 'portkey')
        self.assertEqual(self.org.ai_api_key, 'pk-test-key')
        self.assertEqual(self.org.ai_base_url, 'https://portkey.rutgers.edu/v1')
        self.assertEqual(self.org.ai_model, 'llama-3.1-70b')
        self.assertTrue(response.data['aiEnabled'])
        self.assertTrue(response.data['hasApiKey'])

    def test_patch_portkey_without_api_key(self):
        """Portkey (self-hosted gateway) should work without an API key."""
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su_portkey_nokey@test.edu', 'su_portkey_nokey@test.edu', 'pass')
        payload = {
            'aiProvider': 'portkey',
            'aiBaseUrl': 'http://portkey-gateway.local:8787',
            'aiModel': 'gpt-4o',
        }
        response = request_as('update', su, self.endpoint, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.ai_provider, 'portkey')
        self.assertFalse(self.org.ai_api_key)
        self.assertEqual(self.org.ai_model, 'gpt-4o')
        self.assertTrue(response.data['aiEnabled'])
        self.assertFalse(response.data['hasApiKey'])

    def test_patch_disable_ai(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su5@test.edu', 'su5@test.edu', 'pass')

        # First set up
        request_as('update', su, self.endpoint, {
            'aiProvider': 'gemini', 'aiApiKey': 'key', 'aiModel': 'gemini-2.5-flash',
        })

        # Now disable
        response = request_as('update', su, self.endpoint, {'aiDisabled': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['aiEnabled'])
        self.assertFalse(response.data['aiCommentsEnabled'])

    # ------------------------------------------------------------------
    # Course policy
    # ------------------------------------------------------------------

    def test_patch_course_policy_all(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su6@test.edu', 'su6@test.edu', 'pass')
        response = request_as('update', su, self.endpoint, {'aiCoursePolicy': 'all'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.ai_course_policy, 'all')

    def test_patch_course_policy_selected_with_course_ids(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su7@test.edu', 'su7@test.edu', 'pass')

        course = self.DB['Course']
        response = request_as('update', su, self.endpoint, {
            'aiCoursePolicy': 'selected',
            'aiEnabledCourseIds': [course.id],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.ai_course_policy, 'selected')
        self.assertIn(course, self.org.ai_enabled_courses.all())

    def test_selected_policy_ignores_courses_from_other_org(self):
        """Course IDs belonging to other orgs are silently filtered out."""
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su8@test.edu', 'su8@test.edu', 'pass')

        other_org_course = self.DB['Other_Org_Course']
        response = request_as('update', su, self.endpoint, {
            'aiCoursePolicy': 'selected',
            'aiEnabledCourseIds': [other_org_course.id],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The other-org course should NOT be in the enabled set
        self.assertEqual(self.org.ai_enabled_courses.count(), 0)

    def test_patch_course_policy_none(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su9@test.edu', 'su9@test.edu', 'pass')
        response = request_as('update', su, self.endpoint, {'aiCoursePolicy': 'none'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.ai_course_policy, 'none')

    # ------------------------------------------------------------------
    # Per-feature model overrides (aiFeatureModels)
    # ------------------------------------------------------------------

    def test_patch_ai_feature_models_persists(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su10@test.edu', 'su10@test.edu', 'pass')

        response = request_as('update', su, self.endpoint, {
            'aiFeatureModels': {'quiz_generation': 'gemini-2.5-pro'},
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['aiFeatureModels'], {'quiz_generation': 'gemini-2.5-pro'})
        self.org.refresh_from_db()
        self.assertEqual(self.org.ai_feature_models, {'quiz_generation': 'gemini-2.5-pro'})

    def test_patch_ai_feature_models_rejects_unknown_key(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su11@test.edu', 'su11@test.edu', 'pass')

        response = request_as('update', su, self.endpoint, {
            'aiFeatureModels': {'not_a_feature': 'gpt-4o'},
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_ai_feature_models_rejects_non_string_value(self):
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su12@test.edu', 'su12@test.edu', 'pass')

        response = request_as('update', su, self.endpoint, {
            'aiFeatureModels': {'quiz_generation': 42},
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_ai_feature_models_drops_empty_values(self):
        """Empty-string values mean 'clear the override' and are not stored."""
        from django.contrib.auth.models import User
        su = User.objects.create_superuser('su13@test.edu', 'su13@test.edu', 'pass')

        request_as('update', su, self.endpoint, {
            'aiFeatureModels': {'quiz_generation': 'gemini-2.5-pro'},
        })
        response = request_as('update', su, self.endpoint, {
            'aiFeatureModels': {'quiz_generation': ''},
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.ai_feature_models, {})
