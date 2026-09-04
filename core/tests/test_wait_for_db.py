# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import OperationalError
from django.test import SimpleTestCase


class WaitForDbCommandTests(SimpleTestCase):
    """`manage.py wait_for_db` retries until the DB answers, then gives up on timeout."""

    @mock.patch('core.management.commands.wait_for_db.time.sleep')
    @mock.patch('core.management.commands.wait_for_db.connections')
    def test_retries_until_connection_succeeds(self, connections, sleep):
        conn = connections['default']
        conn.ensure_connection.side_effect = [OperationalError('down'), OperationalError('down'), None]

        out = StringIO()
        call_command('wait_for_db', timeout=30, stdout=out)

        self.assertEqual(conn.ensure_connection.call_count, 3)
        # Backoff: 1s then 2s between the three attempts.
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])
        conn.close.assert_called_once()
        self.assertIn('database ready after 3 attempt(s)', out.getvalue())

    @mock.patch('core.management.commands.wait_for_db.time.sleep')
    @mock.patch('core.management.commands.wait_for_db.time.monotonic', side_effect=[0, 400])
    @mock.patch('core.management.commands.wait_for_db.connections')
    def test_gives_up_after_timeout(self, connections, monotonic, sleep):
        connections['default'].ensure_connection.side_effect = OperationalError('down')

        with self.assertRaises(CommandError):
            call_command('wait_for_db', timeout=300, stdout=StringIO())
        sleep.assert_not_called()
