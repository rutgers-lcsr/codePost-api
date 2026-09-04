# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""OAuth 2.1 Bearer authentication for the MCP endpoint.

The MCP auth spec (2025-06-18) requires the 401 challenge to point at the
RFC 9728 protected-resource metadata; django-oauth-toolkit's
``OAuth2ProtectedResourceAuthentication`` does exactly that, and this subclass
pins the advertised URL to the path-component form for ``/mcp`` (the resource
is the MCP endpoint, not the whole API).

This class must be FIRST in the view's ``authentication_classes``: DRF takes
the 401 ``WWW-Authenticate`` header from the first authenticator, and this one
safely returns ``None`` for non-Bearer credentials, so CourseKey / JWT /
personal-token requests fall through to the existing classes untouched.
"""
from __future__ import annotations

from django.conf import settings
from oauth2_provider.contrib.rest_framework import \
    OAuth2ProtectedResourceAuthentication


class MCPOAuth2Authentication(OAuth2ProtectedResourceAuthentication):

    def get_resource_metadata_url(self, request):
        return f"{settings.API_URL}/.well-known/oauth-protected-resource/mcp"
