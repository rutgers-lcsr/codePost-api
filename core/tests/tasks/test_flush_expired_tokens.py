# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for the flush_expired_tokens beat sweep."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from core.tasks import flush_expired_tokens
from core.tests.factories import UserFactory


def _token(user, expires_in_days, jti):
  return OutstandingToken.objects.create(
      user=user,
      jti=jti,
      token=f'token-{jti}',
      created_at=timezone.now() - timedelta(days=14),
      expires_at=timezone.now() + timedelta(days=expires_in_days),
  )


class TestFlushExpiredTokens(TestCase):

  def setUp(self):
    self.user = UserFactory()

  def test_deletes_expired_tokens(self):
    _token(self.user, expires_in_days=-1, jti='expired')
    self.assertEqual(flush_expired_tokens(), 1)
    self.assertFalse(OutstandingToken.objects.exists())

  def test_cascade_deletes_blacklist_rows(self):
    expired = _token(self.user, expires_in_days=-1, jti='expired-blacklisted')
    BlacklistedToken.objects.create(token=expired)
    # delete() counts both the outstanding row and its cascaded blacklist row
    self.assertEqual(flush_expired_tokens(), 2)
    self.assertFalse(OutstandingToken.objects.exists())
    self.assertFalse(BlacklistedToken.objects.exists())

  def test_keeps_unexpired_tokens(self):
    _token(self.user, expires_in_days=7, jti='live')
    live_blacklisted = _token(self.user, expires_in_days=7, jti='live-blacklisted')
    BlacklistedToken.objects.create(token=live_blacklisted)
    self.assertEqual(flush_expired_tokens(), 0)
    self.assertEqual(OutstandingToken.objects.count(), 2)
    self.assertEqual(BlacklistedToken.objects.count(), 1)

  def test_empty_table_returns_zero(self):
    self.assertEqual(flush_expired_tokens(), 0)
