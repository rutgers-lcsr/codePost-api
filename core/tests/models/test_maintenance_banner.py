# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Robust tests for MaintenanceBanner model.

Covers:
- Singleton pattern (always pk=1)
- is_active_now() with schedule windows
- Default values
- Load-or-create behavior
- Severity choices
"""
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from core.models import MaintenanceBanner


class TestMaintenanceBannerSingleton(TestCase):
    """The MaintenanceBanner is always pk=1 — a singleton."""

    def test_save_always_uses_pk_1(self):
        """No matter what pk is attempted, it saves as pk=1."""
        banner = MaintenanceBanner()
        banner.pk = 999
        banner.save()
        self.assertEqual(banner.pk, 1)

    def test_only_one_instance_ever_exists(self):
        """Multiple saves overwrite the same row."""
        MaintenanceBanner(message="First").save()
        MaintenanceBanner(message="Second").save()
        self.assertEqual(MaintenanceBanner.objects.count(), 1)
        self.assertEqual(MaintenanceBanner.objects.get(pk=1).message, "Second")

    def test_load_creates_if_not_exists(self):
        """MaintenanceBanner.load() creates a default instance if none exists."""
        self.assertEqual(MaintenanceBanner.objects.count(), 0)
        banner = MaintenanceBanner.load()
        self.assertEqual(MaintenanceBanner.objects.count(), 1)
        self.assertFalse(banner.active)

    def test_load_returns_existing(self):
        """MaintenanceBanner.load() returns the existing pk=1 row."""
        MaintenanceBanner(message="Existing", active=True).save()
        banner = MaintenanceBanner.load()
        self.assertEqual(banner.message, "Existing")
        self.assertTrue(banner.active)


class TestMaintenanceBannerSchedule(TestCase):
    """is_active_now() with time windows."""

    def test_inactive_banner_returns_false(self):
        """active=False -> is_active_now() is False regardless of schedule."""
        banner = MaintenanceBanner(active=False)
        banner.save()
        self.assertFalse(banner.is_active_now())

    def test_active_no_schedule_returns_true(self):
        """active=True with no starts_at/ends_at -> always active."""
        banner = MaintenanceBanner(active=True, starts_at=None, ends_at=None)
        banner.save()
        self.assertTrue(banner.is_active_now())

    def test_active_before_starts_at_returns_false(self):
        """active=True but current time is before starts_at -> not active yet."""
        future = timezone.now() + timedelta(hours=1)
        banner = MaintenanceBanner(active=True, starts_at=future)
        banner.save()
        self.assertFalse(banner.is_active_now())

    def test_active_after_ends_at_returns_false(self):
        """active=True but current time is after ends_at -> expired."""
        past = timezone.now() - timedelta(hours=1)
        banner = MaintenanceBanner(active=True, ends_at=past)
        banner.save()
        self.assertFalse(banner.is_active_now())

    def test_active_within_schedule_returns_true(self):
        """active=True within starts_at..ends_at window -> active."""
        now = timezone.now()
        banner = MaintenanceBanner(
            active=True,
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
        banner.save()
        self.assertTrue(banner.is_active_now())

    def test_str_representation(self):
        """__str__ shows ACTIVE or inactive status."""
        banner = MaintenanceBanner(active=True)
        banner.save()
        self.assertIn("ACTIVE", str(banner))
        banner.active = False
        banner.save()
        self.assertIn("inactive", str(banner))


class TestMaintenanceBannerDefaults(TestCase):
    """Default value tests."""

    def test_default_severity_is_info(self):
        banner = MaintenanceBanner.load()
        self.assertEqual(banner.severity, MaintenanceBanner.SEVERITY_INFO)

    def test_default_color(self):
        banner = MaintenanceBanner.load()
        self.assertEqual(banner.color, "#0e704c")

    def test_valid_severity_choices(self):
        banner = MaintenanceBanner.load()
        for sev_code, _ in MaintenanceBanner.SEVERITY_CHOICES:
            banner.severity = sev_code
            banner.save()
            banner.refresh_from_db()
            self.assertEqual(banner.severity, sev_code)
