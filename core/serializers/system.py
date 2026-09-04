# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers


class HealthCheckSerializer(serializers.Serializer):
    """Result of a single health probe."""
    status = serializers.ChoiceField(choices=['ok', 'warning', 'error'])
    label = serializers.CharField()  # type: ignore[assignment]  # DRF field overrides base property
    detail = serializers.CharField(allow_null=True, allow_blank=True)
    latency_ms = serializers.FloatField(allow_null=True, required=False)


class DatabaseCheckSerializer(HealthCheckSerializer):
    connections_current = serializers.IntegerField(allow_null=True, required=False)
    connections_max_used = serializers.IntegerField(allow_null=True, required=False)
    connections_limit = serializers.IntegerField(allow_null=True, required=False)


class DiskCheckSerializer(HealthCheckSerializer):
    used_pct = serializers.FloatField(allow_null=True, required=False)
    free_gb = serializers.FloatField(allow_null=True, required=False)


class CeleryCheckSerializer(HealthCheckSerializer):
    worker_count = serializers.IntegerField(allow_null=True, required=False)


class MigrationCheckSerializer(HealthCheckSerializer):
    pending = serializers.IntegerField()


class SystemHealthResponseSerializer(serializers.Serializer):
    checked_at = serializers.DateTimeField()
    overall = serializers.ChoiceField(choices=['ok', 'degraded', 'critical'])
    database = DatabaseCheckSerializer()
    celery = CeleryCheckSerializer()
    cache = HealthCheckSerializer()
    migrations = MigrationCheckSerializer()
    disk = DiskCheckSerializer()
    recent_events_1h = serializers.IntegerField()

class SystemActivityResponseSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField())
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()


class MaintenanceBannerSerializer(serializers.Serializer):
    active = serializers.BooleanField(required=False)
    message = serializers.CharField(required=False, allow_blank=True)
    color = serializers.CharField(required=False, max_length=30)
    severity = serializers.ChoiceField(
        choices=['info', 'warning', 'critical'],
        required=False,
    )
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    ends_at = serializers.DateTimeField(required=False, allow_null=True)


class MaintenanceBannerResponseSerializer(serializers.Serializer):
    """Full response shape returned by both GET and PATCH /system/banner/."""
    active = serializers.BooleanField()
    active_now = serializers.BooleanField(help_text="True when active=True and within the schedule window.")
    message = serializers.CharField()
    color = serializers.CharField()
    severity = serializers.ChoiceField(choices=['info', 'warning', 'critical'])
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
