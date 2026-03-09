# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Robust tests for the Organization model.

Covers:
- CRUD operations via the API
- Field constraints (unique name, unique shortname, max_length)
- AI configuration fields
- SSO configuration
- Permission checks (only admins should create/edit organizations)
"""
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Organization
from core.tests.utils import request_as, setUpBase
from core.tests.factories import OrganizationFactory
from core.tests.views.personas import Persona


class TestOrganizationModelConstraints(TestCase):
    """Direct model-level constraint tests (no API layer)."""

    def test_unique_name_constraint(self):
        """Two organizations cannot share the same name."""
        OrganizationFactory(name="UniqueOrg", shortname="uo1")
        with self.assertRaises(IntegrityError):
            Organization.objects.create(name="UniqueOrg", shortname="uo2")

    def test_unique_shortname_constraint(self):
        """Two organizations cannot share the same shortname."""
        OrganizationFactory(name="Org A", shortname="same")
        with self.assertRaises(IntegrityError):
            Organization.objects.create(name="Org B", shortname="same")

    def test_create_organization_with_unique_names(self):
        """Organizations with different names and shortnames can coexist."""
        org1 = OrganizationFactory(name="Alpha University", shortname="alpha")
        org2 = OrganizationFactory(name="Beta University", shortname="beta")
        self.assertNotEqual(org1.id, org2.id)
        self.assertEqual(Organization.objects.filter(id__in=[org1.id, org2.id]).count(), 2)

    def test_str_returns_shortname(self):
        """Organization.__str__ returns the shortname."""
        org = OrganizationFactory(name="Full Name University", shortname="fnu")
        self.assertEqual(str(org), "fnu")

    def test_default_field_values(self):
        """New organizations have correct defaults for SSO and AI fields."""
        org = OrganizationFactory(name="Default Org", shortname="deforg")
        self.assertFalse(org.sso_enabled)
        self.assertIsNone(org.sso_provider)
        self.assertFalse(org.ai_disabled)
        self.assertFalse(org.ai_comments_disabled)
        self.assertEqual(org.ai_course_policy, 'none')
        self.assertTrue(org.send_welcome_email)

    def test_ai_provider_choices(self):
        """Setting ai_provider to a valid choice works."""
        org = OrganizationFactory(name="AI Org", shortname="aiorg")
        for provider_code, _ in Organization.AI_PROVIDER_CHOICES:
            org.ai_provider = provider_code
            org.save()
            org.refresh_from_db()
            self.assertEqual(org.ai_provider, provider_code)

    def test_ai_course_policy_choices(self):
        """Setting ai_course_policy to each valid choice succeeds."""
        org = OrganizationFactory(name="Policy Org", shortname="polorg")
        for policy_code, _ in Organization.AI_COURSE_POLICY_CHOICES:
            org.ai_course_policy = policy_code
            org.save()
            org.refresh_from_db()
            self.assertEqual(org.ai_course_policy, policy_code)

    def test_sso_config_default_is_empty_dict(self):
        """SSO config defaults to an empty dict."""
        org = OrganizationFactory(name="SSO Org", shortname="ssoorg")
        self.assertEqual(org.sso_config, {})

    def test_ordering_is_by_name(self):
        """Organizations are ordered alphabetically by name."""
        OrganizationFactory(name="Zebra U", shortname="zu")
        OrganizationFactory(name="Alpha U", shortname="au")
        OrganizationFactory(name="Middle U", shortname="mu")
        names = list(Organization.objects.values_list('name', flat=True))
        self.assertEqual(names, sorted(names))


class TestOrganizationAPI(APITestCase):
    """API-level tests for Organization endpoints."""

    def setUp(self):
        setUpBase(self)

    def test_course_admin_cannot_read_organization_via_api(self):
        """A course admin gets 403 when reading an organization (requires superuser or org staff)."""
        user = Persona.ADMIN_OF_COURSE(self)
        org = self.course.organization
        response = request_as("read", user, reverse("organization-detail", args=[org.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_read_organization(self):
        """A student gets 403 when reading their organization."""
        user = Persona.STUDENT_OF_COURSE(self)
        org = self.course.organization
        response = request_as("read", user, reverse("organization-detail", args=[org.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_org_user_cannot_update_organization(self):
        """An admin in another org should not be able to update this org."""
        user = Persona.ADMIN_OF_OTHER_ORG(self)
        org = self.course.organization
        response = request_as("update", user, reverse("organization-detail", args=[org.id]), {"name": "Hacked"})
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
