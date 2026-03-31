# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import CourseAuditEvent


class CourseAuditEventSerializer(serializers.ModelSerializer):
    """Read-only serializer for course audit events."""
    userEmail = serializers.SerializerMethodField()
    assignmentName = serializers.SerializerMethodField()
    eventType = serializers.CharField(source='event_type', read_only=True)

    class Meta:
        model = CourseAuditEvent
        fields = (
            'id',
            'course',
            'assignment',
            'submission',
            'user',
            'userEmail',
            'assignmentName',
            'eventType',
            'meta',
            'created',
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField)
    def get_userEmail(self, obj):
        return obj.user.email if obj.user else None

    @extend_schema_field(serializers.CharField)
    def get_assignmentName(self, obj):
        return obj.assignment.name if obj.assignment else None
