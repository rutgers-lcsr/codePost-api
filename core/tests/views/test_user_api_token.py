# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase, APIClient

from core.tests.factories import AdminFactory, UserFactory


class TestUserRequestApiToken(APITestCase):
  endpoint = '/users/requestAPIToken/'

  def _client_for(self, user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client

  def test_repeated_request_api_token_keeps_single_token_row(self):
    admin = AdminFactory()
    client = self._client_for(admin)

    first = client.post(self.endpoint, {}, format='json')
    self.assertEqual(getattr(first, 'status_code', None), status.HTTP_200_OK)

    second = client.post(self.endpoint, {}, format='json')
    self.assertEqual(getattr(second, 'status_code', None), status.HTTP_200_OK)

    self.assertEqual(Token.objects.filter(user=admin).count(), 1)
    admin.refresh_from_db()
    self.assertIsNotNone(admin.profile.api_token)

  def test_request_api_token_recovers_from_stale_profile_pointer(self):
    admin = AdminFactory()
    client = self._client_for(admin)

    # Simulate a stale profile reference with an existing token row still in DB.
    stale_token = Token.objects.create(user=admin)
    admin.profile.api_token = None
    admin.profile.save(update_fields=['api_token'])

    response = client.post(self.endpoint, {}, format='json')
    self.assertEqual(getattr(response, 'status_code', None), status.HTTP_200_OK)

    self.assertFalse(Token.objects.filter(pk=stale_token.pk).exists())
    self.assertEqual(Token.objects.filter(user=admin).count(), 1)

  def test_request_api_token_requires_auth(self):
    response = APIClient().post(self.endpoint, {}, format='json')
    self.assertEqual(getattr(response, 'status_code', None), status.HTTP_401_UNAUTHORIZED)

  def test_request_api_token_requires_roster_permission(self):
    user = UserFactory()
    user.profile.canModifyRosters = False
    user.profile.save(update_fields=['canModifyRosters'])

    response = self._client_for(user).post(self.endpoint, {}, format='json')
    self.assertEqual(getattr(response, 'status_code', None), status.HTTP_403_FORBIDDEN)
