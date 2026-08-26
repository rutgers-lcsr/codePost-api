# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers

from core.models import COURSE_API_KEY_SCOPE_CHOICES, CourseAPIKey


class CourseAPIKeyReadSerializer(serializers.ModelSerializer):
    """Read-only representation of a course API key (never exposes the full key)."""

    createdBy = serializers.CharField(source="created_by.username", read_only=True, allow_null=True)

    class Meta:
        model = CourseAPIKey
        fields = [
            "id",
            "name",
            "keyPrefix",
            "isActive",
            "scope",
            "lastUsedAt",
            "createdBy",
            "created",
            "modified",
        ]
        # Map camelCase API names to snake_case model fields
        extra_kwargs = {
            "keyPrefix": {"source": "key_prefix"},
            "isActive": {"source": "is_active"},
            "lastUsedAt": {"source": "last_used_at"},
        }


class CourseAPIKeyCreateSerializer(serializers.Serializer):
    """Input serializer for creating a new course API key."""

    name = serializers.CharField(max_length=128)
    # Defaults to the safest option: a key that can only read. Agent tools above
    # a key's scope are never advertised to it, so this is the real guardrail.
    scope = serializers.ChoiceField(
        choices=COURSE_API_KEY_SCOPE_CHOICES, default="read", required=False)


class CourseAPIKeyCreateResponseSerializer(serializers.Serializer):
    """Response serializer that includes the raw key (shown only once)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    key = serializers.CharField(help_text="The full API key. This is only shown once.")
    keyPrefix = serializers.CharField()
    scope = serializers.CharField()
    createdBy = serializers.CharField()
    created = serializers.DateTimeField()


class PendingAgentActionSerializer(serializers.ModelSerializer):
    """Dashboard rows for Tier-3 agent confirmations — includes the code, so
    this serializer must only ever be reachable by a human course admin."""

    expiresAt = serializers.DateTimeField(source="expires_at", read_only=True)
    requestedBy = serializers.CharField(source="requested_by.username",
                                        read_only=True, allow_null=True)
    # The legacy `jsonfield` package's field is opaque to DRF (it would render
    # the dict as a Python-repr string); surface the real object.
    plan = serializers.SerializerMethodField()

    def get_plan(self, obj):
        return obj.plan if isinstance(obj.plan, dict) else {}

    class Meta:
        from core.models import PendingAgentAction
        model = PendingAgentAction
        fields = ["id", "tool", "code", "plan", "expiresAt", "requestedBy",
                  "created"]
        read_only_fields = fields
