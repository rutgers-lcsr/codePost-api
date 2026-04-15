# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers

from core.models import CourseAPIKey


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


class CourseAPIKeyCreateResponseSerializer(serializers.Serializer):
    """Response serializer that includes the raw key (shown only once)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    key = serializers.CharField(help_text="The full API key. This is only shown once.")
    keyPrefix = serializers.CharField()
    createdBy = serializers.CharField()
    created = serializers.DateTimeField()
