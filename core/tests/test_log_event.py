# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from unittest import mock

from django.db.utils import OperationalError
from django.test import TestCase

from core.logging import logEvent


class LogEventDependencyOutageTests(TestCase):
    """logEvent must not email the admins once per request for the length of a DB outage."""

    @mock.patch('core.logging.DEBUG', False)
    @mock.patch('core.emails.CodepostAPIErrorEmail.send_email')
    @mock.patch('core.logging.Event.objects.create', side_effect=OperationalError('MySQL server has gone away'))
    def test_database_outage_does_not_email(self, _create, send_email):
        logEvent("API Error")
        send_email.assert_not_called()

    @mock.patch('core.logging.DEBUG', False)
    @mock.patch('core.emails.CodepostAPIErrorEmail.send_email')
    @mock.patch('core.logging.Event.objects.create', side_effect=RuntimeError('boom'))
    def test_other_failures_still_email(self, _create, send_email):
        logEvent("API Error")
        send_email.assert_called_once()
