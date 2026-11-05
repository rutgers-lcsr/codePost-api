# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""POST /organizations/{id}/reset_user_password/ reports what actually happened to the email."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Organization

LOCMEM = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


class TestOrgResetUserPassword(APITestCase):

  def setUp(self):
    self.organization = Organization.objects.create(name="Princeton", shortname="princeton")
    self.org_staff = User.objects.create_user(
        username='orgstaff@princeton.edu', email='orgstaff@princeton.edu', password='TestPass1!')
    self.org_staff.profile.organization = self.organization
    self.org_staff.profile.isOrgStaff = True
    self.org_staff.profile.save()
    self.member = User.objects.create_user(
        username='member@princeton.edu', email='member@princeton.edu', password='TestPass1!')
    self.member.profile.organization = self.organization
    self.member.profile.save()
    self.url = f'/organizations/{self.organization.pk}/reset_user_password/'
    self.client.force_authenticate(user=self.org_staff)

  def _post(self):
    return self.client.post(self.url, {'user_email': 'member@princeton.edu'}, format='json')

  @override_settings(MAILERS=LOCMEM)
  def test_reset_email_is_delivered_and_reported(self):
    with patch('core.emails.TESTING', False), patch('core.emails.OVERRIDE_EMAIL', ''):
      response = self._post()
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data['status'], 'reset_email_sent')
    self.assertEqual(len(mail.outbox), 1)
    self.assertEqual(mail.outbox[0].to, ['member@princeton.edu'])

  @override_settings(MAILERS=LOCMEM)
  def test_delivery_failure_is_not_reported_as_success(self):
    with patch('core.emails.TESTING', False), patch('core.emails.OVERRIDE_EMAIL', ''), \
         patch('django.core.mail.EmailMessage.send', side_effect=OSError('smtp down')):
      response = self._post()
    self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
    self.assertIsInstance(response.data['detail'], str)
    self.assertNotIn('reset_email_sent', str(response.data))
    self.assertNotIn('smtp down', str(response.data))

  def test_unexpected_exception_is_not_leaked(self):
    with patch('core.emails.PasswordResetEmail.send_email', side_effect=ValueError('secret internal')):
      response = self._post()
    self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    self.assertIsInstance(response.data['detail'], str)
    self.assertNotIn('secret internal', str(response.data))
