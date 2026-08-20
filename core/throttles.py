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


class AIConnectionTestThrottle(UserRateThrottle):
    """Rate limit for AI provider connection tests (each fires a real, paid LLM call)."""
    scope = 'ai_connection_test'
    rate = '10/minute'

    def allow_request(self, request, view):
        if settings.TESTING:
            return True
        return super().allow_request(request, view)


class AgentToolThrottle(UserRateThrottle):
    """Rate limit for MCP agent tool calls.

    Keyed on ``request.user.pk``, which for a course API key is that course's
    service account — so this is a per-course budget and one runaway agent
    loop cannot starve another course.

    Both ``scope`` and ``rate`` are set: there is no ``DEFAULT_THROTTLE_RATES``
    in settings, so a scope-only throttle would raise at init.
    """
    scope = 'agent_tool'
    rate = '120/minute'

    def allow_request(self, request, view):
        if settings.TESTING:
            return True
        return super().allow_request(request, view)


class AgentWriteThrottle(AgentToolThrottle):
    """Tighter budget for agent-initiated writes, same per-course keying."""
    scope = 'agent_write'
    rate = '20/minute'
