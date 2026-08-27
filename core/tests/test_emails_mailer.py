# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Guards the MAILERS-based email configuration (Django 6.1): a CodepostEmail
subclass must deliver through the default mailer. TESTING and OVERRIDE_EMAIL
are module-level constants in core.emails, so they are patched there.
"""
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from core.emails import UserAddedToCourseEmail
from core.tests.factories import OrganizationFactory, StudentFactory


class TestDefaultMailerDelivery(APITestCase):

  @override_settings(MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}})
  def test_email_sends_through_default_mailer(self):
    org = OrganizationFactory()
    user = StudentFactory(course='mailer', organization=org, count=500)
    with patch('core.emails.TESTING', False), \
         patch('core.emails.OVERRIDE_EMAIL', 'override@example.com'):
      UserAddedToCourseEmail(user=user).send_email("MailCourse", "F2026", "student", force_send=True)
    self.assertEqual(len(mail.outbox), 1)
    self.assertEqual(mail.outbox[0].to, ["override@example.com"])
    self.assertEqual(mail.outbox[0].subject, "You have been added to a course on CodePost")
