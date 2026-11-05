# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Recipient selection for the emails that go to org staff and CodePost admins."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from core.emails import CodepostAPIErrorEmail, NewAdminRequestEmail
from core.models import Organization

LOCMEM = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}


class TestAdminEmailRecipients(APITestCase):

  def setUp(self):
    self.org = Organization.objects.create(name="Princeton", shortname="princeton")
    self.requester = self._user('requester@princeton.edu')
    self.staff = self._user('staff@princeton.edu', staff=True)
    self._user('gone@princeton.edu', staff=True, active=False)
    self._user('', staff=True, username='noemail')

  def _user(self, email, staff=False, active=True, username=None):
    user = User.objects.create_user(username=username or email, email=email, password='TestPass1!')
    user.is_active = active
    user.save()
    user.profile.organization = self.org
    user.profile.isOrgStaff = staff
    user.profile.save()
    return user

  def test_org_staff_and_codepost_admins_receive_admin_requests(self):
    with patch('core.emails.OVERRIDE_EMAIL', ''), \
         patch('core.emails.ADMINS', ['ops@example.com', 'dev@example.com']):
      recipients = NewAdminRequestEmail(self.requester).get_admin_emails()
    # Active org staff with an address, then the full CodePost admin addresses.
    self.assertEqual(recipients, ['staff@princeton.edu', 'ops@example.com', 'dev@example.com'])

  @override_settings(MAILERS=LOCMEM)
  def test_override_email_redirects_admin_request(self):
    with patch('core.emails.TESTING', False), \
         patch('core.emails.OVERRIDE_EMAIL', 'sink@example.com'), \
         patch('core.emails.ADMINS', ['ops@example.com']):
      NewAdminRequestEmail(self.requester).send_email('Princeton')
    self.assertEqual(len(mail.outbox), 1)
    self.assertEqual(mail.outbox[0].to, ['sink@example.com'])

  @override_settings(MAILERS=LOCMEM)
  def test_override_email_redirects_api_error_email(self):
    with patch('core.emails.TESTING', False), \
         patch('core.emails.OVERRIDE_EMAIL', 'sink@example.com'), \
         patch('core.emails.ADMINS', ['ops@example.com']):
      CodepostAPIErrorEmail().send_email('boom', 'details')
    self.assertEqual(len(mail.outbox), 1)
    self.assertEqual(mail.outbox[0].to, ['sink@example.com'])
