# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import CourseAuditEvent


class CourseAuditEventSerializer(serializers.ModelSerializer):
    """Read-only serializer for course audit events."""
    userEmail = serializers.SerializerMethodField()
    assignmentName = serializers.SerializerMethodField()
    quizTitle = serializers.SerializerMethodField()
    eventType = serializers.CharField(source='event_type', read_only=True)

    class Meta:
        model = CourseAuditEvent
        fields = (
            'id',
            'course',
            'assignment',
            'submission',
            'quiz',
            'user',
            'userEmail',
            'assignmentName',
            'quizTitle',
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

    @extend_schema_field(serializers.CharField)
    def get_quizTitle(self, obj):
        # Fall back to the snapshotted title in meta for deleted quizzes.
        if obj.quiz_id and obj.quiz:
            return obj.quiz.title
        return (obj.meta or {}).get('title') if isinstance(obj.meta, dict) else None
