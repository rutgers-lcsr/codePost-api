# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.models import CourseAPIKey
from core.services.course_api_key import get_or_create_course_service_user


class CourseAPIKeyAuthentication(BaseAuthentication):
    """Authenticate requests using an ``Authorization: CourseKey <raw_key>`` header.

    On success the request is associated with the course's service user and
    ``request.auth`` is set to a dict containing ``course_scope_id``.
    """

    keyword = "CourseKey"

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith(f"{self.keyword} "):
            return None

        raw_key = auth_header[len(self.keyword) + 1:].strip()
        if not raw_key:
            return None

        # Extract prefix for fast DB lookup (everything up to and including
        # the second underscore, e.g. ``cpk_123_``)
        parts = raw_key.split("_", 2)
        if len(parts) < 3 or parts[0] != "cpk":
            raise AuthenticationFailed("Invalid course API key format.")

        prefix = f"{parts[0]}_{parts[1]}_"

        candidates = CourseAPIKey.objects.select_related("course").filter(
            key_prefix=prefix, is_active=True,
        )

        api_key = None
        for candidate in candidates:
            if candidate.verify(raw_key):
                api_key = candidate
                break

        if api_key is None:
            raise AuthenticationFailed("Invalid or revoked course API key.")

        # Update last_used_at (fire-and-forget, no extra SELECT via update())
        CourseAPIKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())

        service_user = get_or_create_course_service_user(api_key.course)
        # api_key_id/scope let the agent layer resolve how much this key may do
        # without a second lookup; ordinary views only ever read course_scope_id.
        auth_info = {
            "course_scope_id": api_key.course_id,
            "api_key_id": api_key.pk,
            "scope": api_key.scope,
        }
        return (service_user, auth_info)

    def authenticate_header(self, request):
        return self.keyword


class CourseScopedJWTAuthentication(JWTAuthentication):
    """Extends standard JWT auth to propagate an optional ``course_id`` claim.

    If the validated token contains a ``course_id`` claim, the auth info
    dict attached to ``request.auth`` will include ``course_scope_id``.
    Tokens without the claim behave exactly like standard JWTs.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result

        course_id = validated_token.get("course_id")
        if course_id is not None:
            # Wrap the token in a dict-like object that also exposes course_scope_id
            auth_info = CourseScopedTokenInfo(validated_token, course_id)
            return (user, auth_info)

        return result


class CourseScopedTokenInfo:
    """Thin wrapper around a validated JWT token that also carries ``course_scope_id``."""

    def __init__(self, token, course_scope_id):
        self.token = token
        self.course_scope_id = course_scope_id

    def __str__(self):
        return str(self.token)

    def __getitem__(self, key):
        return self.token[key]

    def __contains__(self, key):
        return key in self.token


class CourseAPIKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    """Register the CourseKey auth scheme in the OpenAPI schema."""
    target_class = 'core.authentication.CourseAPIKeyAuthentication'
    name = 'courseKeyAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Course-scoped API key. Format: `CourseKey cpk_<course_id>_<secret>`',
        }

    def get(self, key, default=None):
        return self.token.get(key, default)
