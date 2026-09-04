# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import InterfaceError, OperationalError


class Command(BaseCommand):
    """Block until the default database accepts connections.

    Containers run this before migrate / the celery worker so a database that
    comes up after them (host reboot order, a deploy that recreates the DB) is a
    delay, not a crash loop. Bounded: exits non-zero after --timeout seconds so a
    genuinely broken configuration still surfaces. Each attempt is capped by the
    DATABASES connect_timeout.
    """

    help = "Wait (bounded) for the default database to accept connections."

    def add_arguments(self, parser):
        parser.add_argument('--timeout', type=int, default=300, help="Seconds to keep trying (default 300).")

    def handle(self, *args, **options):
        timeout = options['timeout']
        deadline = time.monotonic() + timeout
        delay, attempt = 1, 0
        while True:
            attempt += 1
            try:
                connections['default'].ensure_connection()
            except (OperationalError, InterfaceError) as exc:
                if time.monotonic() >= deadline:
                    raise CommandError(f"wait_for_db: database unreachable after {timeout}s: {exc}")
                self.stdout.write(f"wait_for_db: attempt {attempt} failed ({exc}); retrying in {delay}s")
                time.sleep(delay)
                delay = min(delay * 2, 10)
            else:
                connections['default'].close()
                self.stdout.write(f"wait_for_db: database ready after {attempt} attempt(s)")
                return
