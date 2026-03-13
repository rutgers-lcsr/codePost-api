# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.

import os

from django.conf import settings


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
        response["Content-Security-Policy"] = frame_ancestors
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
