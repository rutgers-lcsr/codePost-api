# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthAnonRateThrottle(AnonRateThrottle):
    """Rate limit for unauthenticated auth endpoints (login, registration, password reset)."""
    rate = '10/minute'


class AuthUserRateThrottle(UserRateThrottle):
    """Rate limit for authenticated auth endpoints (impersonation, token generation)."""
    rate = '20/minute'
