# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Tests for AIService:
- Config resolution (course own vs org inheritance)
- Cost estimation
- Usage recording
- is_configured property
"""
from types import SimpleNamespace
from typing import cast
from decimal import Decimal

from django.test import TestCase
from django.db.models.signals import post_save

import factory.django

from core.models import Course, Organization, AIUsageRecord
from core.services.ai_service import AIService, GenerationResult
from core.tests.factories import (
    CourseFactory,
    OrganizationFactory,
    AdminFactory,
)


# ---------------------------------------------------------------------------
# Helpers — build lightweight namespace objects for pure-unit tests where we
# don't need the database but DO need the same attribute interface.
# ---------------------------------------------------------------------------

def _make_org(**overrides):
    defaults = dict(
        ai_provider=None,
        ai_api_key=None,
        ai_base_url=None,
        ai_model=None,
        ai_disabled=False,
        ai_comments_disabled=False,
        ai_course_policy='none',
        ai_enabled_courses=SimpleNamespace(filter=lambda **kw: SimpleNamespace(exists=lambda: False)),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_course(**overrides):
    defaults = dict(
        pk=999,
        ai_provider=None,
        ai_api_key=None,
        ai_base_url=None,
        ai_model=None,
        ai_disabled=False,
        ai_comments_disabled=False,
        ai_use_own_settings=False,
        organization=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ===========================================================================
# Pure unit tests (no DB required)
# ===========================================================================

class TestAIServiceConfigResolution(TestCase):
    """Test that AIService.__init__ correctly resolves config based on
    course.ai_use_own_settings and organization settings."""

    # --- Course uses its own key ---

    def test_course_uses_own_when_flag_true_and_provider_set(self):
        course = _make_course(
            ai_use_own_settings=True,
            ai_provider='openai',
            ai_api_key='course-key',
            ai_model='gpt-4o',
        )
        svc = AIService(cast(Course, course))
        self.assertEqual(svc.provider, 'openai')
        self.assertEqual(svc.api_key, 'course-key')
        self.assertEqual(svc.model, 'gpt-4o')
        self.assertTrue(svc.is_configured)

    def test_course_use_own_true_no_provider_falls_through(self):
        """ai_use_own_settings=True but no provider → uses course fields (empty)."""
        course = _make_course(ai_use_own_settings=True)
        svc = AIService(cast(Course, course))
        self.assertIsNone(svc.provider)
        self.assertFalse(svc.is_configured)

    # --- Org inheritance (course.ai_use_own_settings=False) ---

    def test_inherits_from_org_when_policy_all(self):
        org = _make_org(
            ai_provider='gemini',
            ai_api_key='org-key',
            ai_model='gemini-2.5-flash',
            ai_course_policy='all',
        )
        course = _make_course(ai_use_own_settings=False, organization=org)
        svc = AIService(cast(Course, course))
        self.assertEqual(svc.provider, 'gemini')
        self.assertEqual(svc.api_key, 'org-key')
        self.assertEqual(svc.model, 'gemini-2.5-flash')
        self.assertTrue(svc.is_configured)

    def test_inherits_from_org_when_policy_selected_and_course_in_list(self):
        """When policy='selected' and the course IS in the enabled list."""
        org = _make_org(
            ai_provider='openai',
            ai_api_key='org-openai-key',
            ai_model='gpt-4o-mini',
            ai_course_policy='selected',
            # Simulate the M2M filter returning True
            ai_enabled_courses=SimpleNamespace(
                filter=lambda **kw: SimpleNamespace(exists=lambda: True)
            ),
        )
        course = _make_course(ai_use_own_settings=False, organization=org)
        svc = AIService(cast(Course, course))
        self.assertEqual(svc.provider, 'openai')
        self.assertEqual(svc.api_key, 'org-openai-key')

    def test_does_not_inherit_when_policy_selected_and_course_not_in_list(self):
        """When policy='selected' but the course is NOT in the enabled list,
        falls back to course fields (empty)."""
        org = _make_org(
            ai_provider='openai',
            ai_api_key='org-key',
            ai_course_policy='selected',
            ai_enabled_courses=SimpleNamespace(
                filter=lambda **kw: SimpleNamespace(exists=lambda: False)
            ),
        )
        course = _make_course(ai_use_own_settings=False, organization=org)
        svc = AIService(cast(Course, course))
        self.assertIsNone(svc.provider)
        self.assertFalse(svc.is_configured)

    def test_does_not_inherit_when_policy_none(self):
        org = _make_org(
            ai_provider='gemini',
            ai_api_key='org-key',
            ai_course_policy='none',
        )
        course = _make_course(ai_use_own_settings=False, organization=org)
        svc = AIService(cast(Course, course))
        self.assertIsNone(svc.provider)
        self.assertFalse(svc.is_configured)

    def test_does_not_inherit_when_org_disabled(self):
        org = _make_org(
            ai_provider='gemini',
            ai_api_key='org-key',
            ai_course_policy='all',
            ai_disabled=True,
        )
        course = _make_course(ai_use_own_settings=False, organization=org)
        svc = AIService(cast(Course, course))
        self.assertIsNone(svc.provider)
        self.assertFalse(svc.is_configured)

    def test_does_not_inherit_when_org_has_no_key(self):
        org = _make_org(
            ai_provider='gemini',
            ai_api_key=None,
            ai_course_policy='all',
        )
        course = _make_course(ai_use_own_settings=False, organization=org)
        svc = AIService(cast(Course, course))
        self.assertIsNone(svc.provider)
        self.assertFalse(svc.is_configured)

    def test_course_with_no_org_uses_own_fields(self):
        """Course not attached to any organization → uses its own fields."""
        course = _make_course(
            ai_use_own_settings=False,
            organization=None,
            ai_provider='gemini',
            ai_api_key='solo-key',
        )
        svc = AIService(cast(Course, course))
        self.assertEqual(svc.provider, 'gemini')
        self.assertEqual(svc.api_key, 'solo-key')
        self.assertTrue(svc.is_configured)

    def test_org_model_provides_default_model(self):
        """When org has a provider but no model, default model is assigned."""
        org = _make_org(
            ai_provider='openai',
            ai_api_key='org-key',
            ai_model=None,
            ai_course_policy='all',
        )
        course = _make_course(ai_use_own_settings=False, organization=org)
        svc = AIService(cast(Course, course))
        self.assertEqual(svc.model, 'gpt-4o-mini')

    def test_course_own_provides_default_model(self):
        """When course has its own provider but no model, default is assigned."""
        course = _make_course(
            ai_use_own_settings=True,
            ai_provider='gemini',
            ai_api_key='key',
            ai_model=None,
        )
        svc = AIService(cast(Course, course))
        self.assertEqual(svc.model, 'gemini-2.5-flash')

    def test_portkey_provider_configures_correctly(self):
        """Portkey provider should resolve with URL and optional key."""
        course = _make_course(
            ai_use_own_settings=True,
            ai_provider='portkey',
            ai_api_key='pk-test-key',
            ai_base_url='https://portkey.rutgers.edu/v1',
            ai_model=None,
        )
        svc = AIService(cast(Course, course))
        self.assertEqual(svc.provider, 'portkey')
        self.assertEqual(svc.api_key, 'pk-test-key')
        self.assertEqual(svc.base_url, 'https://portkey.rutgers.edu/v1')
        self.assertEqual(svc.model, 'default')
        self.assertTrue(svc.is_configured)

    def test_portkey_provider_without_api_key(self):
        """Portkey (self-hosted gateway) should be configured with only a URL, no API key."""
        course = _make_course(
            ai_use_own_settings=True,
            ai_provider='portkey',
            ai_api_key=None,
            ai_base_url='http://portkey-gateway.local:8787',
            ai_model='gpt-4o',
        )
        svc = AIService(cast(Course, course))
        self.assertEqual(svc.provider, 'portkey')
        self.assertFalse(svc.api_key)
        self.assertEqual(svc.base_url, 'http://portkey-gateway.local:8787')
        self.assertEqual(svc.model, 'gpt-4o')
        self.assertTrue(svc.is_configured)


# ===========================================================================
# Cost estimation
# ===========================================================================

class TestEstimateCost(TestCase):
    """Test AIService.estimate_cost static method."""

    def test_known_model_returns_cost(self):
        # gpt-4o-mini: input $0.15/M, output $0.60/M
        cost = AIService.estimate_cost('openai', 'gpt-4o-mini', 1_000_000, 1_000_000)
        self.assertAlmostEqual(cost, 0.75, places=4)

    def test_unknown_model_returns_zero(self):
        cost = AIService.estimate_cost('openai', 'unknown-model', 500, 500)
        self.assertEqual(cost, 0.0)

    def test_ollama_returns_zero(self):
        cost = AIService.estimate_cost('ollama', 'llama3.2', 10000, 10000)
        self.assertEqual(cost, 0.0)

    def test_zero_tokens_returns_zero(self):
        cost = AIService.estimate_cost('openai', 'gpt-4o-mini', 0, 0)
        self.assertEqual(cost, 0.0)

    def test_gemini_flash_cost(self):
        # gemini-2.5-flash: input $0.15/M, output $0.60/M
        cost = AIService.estimate_cost('gemini', 'gemini-2.5-flash', 100_000, 50_000)
        expected = (100_000 / 1_000_000) * 0.15 + (50_000 / 1_000_000) * 0.60
        self.assertAlmostEqual(cost, expected, places=6)


# ===========================================================================
# Usage recording (requires DB)
# ===========================================================================

@factory.django.mute_signals(post_save)
class TestRecordUsage(TestCase):
    """Test AIService.record_usage persists AIUsageRecord."""

    def setUp(self):
        self.org = OrganizationFactory(name='TestOrg', shortname='testorg')
        self.course = CourseFactory(
            name='TestCourse',
            period='s2026',
            organization=self.org,
        )
        self.user = self.course.courseAdmins.first()

        # Configure course with its own AI
        self.course.ai_provider = 'openai'
        self.course.ai_api_key = 'test-key'
        self.course.ai_model = 'gpt-4o-mini'
        self.course.ai_use_own_settings = True
        self.course.save()

    def test_record_usage_creates_record(self):
        svc = AIService(self.course)
        result = GenerationResult(
            text='Some feedback',
            success=True,
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
        )
        svc.record_usage(result, self.user, request_type='comment_generation')

        records = AIUsageRecord.objects.filter(course=self.course)
        self.assertEqual(records.count(), 1)

        record = records.first()
        self.assertEqual(record.provider, 'openai')
        self.assertEqual(record.model, 'gpt-4o-mini')
        self.assertEqual(record.request_type, 'comment_generation')
        self.assertEqual(record.input_tokens, 500)
        self.assertEqual(record.output_tokens, 200)
        self.assertEqual(record.total_tokens, 700)
        self.assertEqual(record.status, 'success')
        self.assertIsNone(record.error_message)
        self.assertEqual(record.user, self.user)
        self.assertEqual(record.organization, self.org)
        self.assertGreater(record.estimated_cost, Decimal('0'))

    def test_record_usage_error_result(self):
        svc = AIService(self.course)
        result = GenerationResult(
            text='',
            success=False,
            error='API rate limit exceeded',
            input_tokens=100,
            output_tokens=0,
            total_tokens=100,
        )
        svc.record_usage(result, self.user, request_type='test_generation')

        record = AIUsageRecord.objects.filter(course=self.course).first()
        self.assertEqual(record.status, 'error')
        self.assertEqual(record.error_message, 'API rate limit exceeded')
        self.assertEqual(record.request_type, 'test_generation')

    def test_record_usage_multiple_creates_multiple_records(self):
        svc = AIService(self.course)
        for i in range(3):
            result = GenerationResult(
                text=f'Feedback {i}', success=True,
                input_tokens=100 * (i + 1), output_tokens=50, total_tokens=100 * (i + 1) + 50,
            )
            svc.record_usage(result, self.user)

        self.assertEqual(AIUsageRecord.objects.filter(course=self.course).count(), 3)
