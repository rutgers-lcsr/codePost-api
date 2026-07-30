# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthAnonRateThrottle(AnonRateThrottle):
    """Rate limit for unauthenticated auth endpoints (login, registration, password reset)."""
    rate = '10/minute'

    def allow_request(self, request, view):
        # Tests hit auth endpoints far faster than any human — all from one client IP,
        # sharing one throttle counter per test process. Under pytest-xdist that made
        # CI flaky (429s whenever enough auth tests landed on the same worker within
        # the window), so throttling is disabled entirely in test runs.
        if settings.TESTING:
            return True
        return super().allow_request(request, view)


class AuthUserRateThrottle(UserRateThrottle):
    """Rate limit for authenticated auth endpoints (impersonation, token generation)."""
    rate = '20/minute'

    def allow_request(self, request, view):
        if settings.TESTING:
            return True
        return super().allow_request(request, view)
