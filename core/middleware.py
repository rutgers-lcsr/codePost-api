# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

import logging
import os

import kombu.exceptions
import redis.exceptions
from django.conf import settings
from django.db.utils import InterfaceError, OperationalError
from django.http import JsonResponse

logger = logging.getLogger(__name__)


# Frame-ancestors origins allowed to embed this site in an iframe.
# Override with CSP_FRAME_ANCESTORS env var (space-separated origins),
# e.g. CSP_FRAME_ANCESTORS="'self' https://*.example.edu https://app.example.edu"
_CSP_FRAME_ANCESTORS_ENV = os.environ.get("CSP_FRAME_ANCESTORS")

if _CSP_FRAME_ANCESTORS_ENV:
    _FRAME_ANCESTORS_ORIGINS = tuple(_CSP_FRAME_ANCESTORS_ENV.split())
else:
    _FRAME_ANCESTORS_ORIGINS = (
        "'self'",
        "https://*.cs.rutgers.edu",
        "https://dev-codepost-1.cs.rutgers.edu",
        "https://dev-codepost-2.cs.rutgers.edu",
        "https://codepost.cs.rutgers.edu",
    )

if settings.DEBUG:
    _FRAME_ANCESTORS_ORIGINS += (
        "http://localhost:3000",
        "http://localhost:8000",
    )


def csp_frame_ancestors_middleware(get_response):
    """
    Sets Content-Security-Policy frame-ancestors to allow embedding in
    iframes from trusted origins. Replaces Django's XFrameOptionsMiddleware.
    """
    frame_ancestors = "frame-ancestors " + " ".join(_FRAME_ANCESTORS_ORIGINS)

    def middleware(request):
        response = get_response(request)
        # The OAuth consent and agent-login pages must never be frameable —
        # a framed consent screen is a clickjacking primitive. Everything else
        # keeps the trusted-origin embedding policy.
        if request.path.startswith(('/o/', '/auth/agent-login')):
            response["Content-Security-Policy"] = "frame-ancestors 'none'"
        else:
            response["Content-Security-Policy"] = frame_ancestors
        return response
    return middleware


def no_cache_middleware(get_response):
    """
    Sets Cache-Control: no-store on all responses to prevent the browser from
    caching authenticated API responses. Without this, switching identities
    (e.g. impersonation) can silently serve stale data from the previous user.
    """
    def middleware(request):
        response = get_response(request)
        response["Cache-Control"] = "no-store"
        return response
    return middleware


# https://www.fusionbox.com/blog/detail/create-react-app-and-django/624/
def dev_cors_middleware(get_response):
    """
    Adds CORS headers for local testing only to allow the frontend, which is served on
    localhost:3000, to access the API, which is served on localhost:8000.
    """
    def middleware(request):
        response = get_response(request)

        response['Access-Control-Allow-Origin'] = 'http://localhost:3000'
        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, OPTIONS, DELETE, HEAD'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken, Authorization'
        response['Access-Control-Allow-Credentials'] = 'true'
        return response
    return middleware


_DEPENDENCY_ERRORS = (
    OperationalError, InterfaceError,                                 # MySQL down / connection lost
    kombu.exceptions.OperationalError,                                # .delay() with the broker down
    redis.exceptions.ConnectionError, redis.exceptions.TimeoutError,  # direct redis use (pubsub, SSE)
)


class DependencyUnavailableMiddleware:
    """
    Answers a database/broker outage with a JSON 503 (+ Retry-After) instead of a
    bare 500, so the SPA can tell "codePost is down" from "no internet" and retry.

    Class-based on purpose: function-style middleware never sees view exceptions.
    DRF re-raises anything that is not an APIException, so DRF and plain Django
    views both land here. Fires under DEBUG too; the traceback still goes to the log.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, _DEPENDENCY_ERRORS):
            return None
        logger.error("dependency unavailable during %s %s: %s", request.method, request.path, exception,
                     exc_info=exception)
        response = JsonResponse({"detail": "codePost is temporarily unavailable. Please retry shortly."}, status=503)
        response["Retry-After"] = "10"
        return response
