# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from __future__ import annotations

import json

from rest_framework import serializers


class LenientJSONField(serializers.JSONField):
    """A JSONField that also accepts JSON-encoded strings.

    Some clients send JSON fields (like arrays) as a string; this field will
    transparently parse them before normal JSON validation.
    """

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception as e:
                raise serializers.ValidationError("Invalid JSON") from e
        return super().to_internal_value(data)


class EnvironmentBuildRequestSerializer(serializers.Serializer):
    language = serializers.CharField(required=False)
    requirements = serializers.CharField(required=False, allow_blank=True)
    dockerfile = serializers.CharField(required=False, allow_blank=True)
    dockerRunInstructions = LenientJSONField(required=False)
    buildType = serializers.CharField(required=False, allow_blank=True)
    autoDetect = serializers.BooleanField(required=False)

    def validate_dockerRunInstructions(self, value):
        if value is None:
            return value
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError(
                "dockerRunInstructions must be a list of strings"
            )
        return value


class EnvironmentBuildResponseSerializer(serializers.Serializer):
    task = serializers.CharField()
    status = serializers.CharField(required=False)
    error = serializers.CharField(required=False)


class EnvironmentBuildStatusResponseSerializer(serializers.Serializer):
    inProgress = serializers.BooleanField()
    isSuccess = serializers.BooleanField()
    logs = serializers.CharField()
    dockerfile = serializers.CharField()
    lastBuilt = serializers.DateTimeField(required=False, allow_null=True)


class EnvironmentBuildStatusErrorSerializer(serializers.Serializer):
    error = serializers.CharField()
    inProgress = serializers.BooleanField()
    isSuccess = serializers.BooleanField()
    logs = serializers.CharField()


class EnvironmentRunAllRequestSerializer(serializers.Serializer):
    sendEmail = serializers.BooleanField(required=False, default=False)


class EnvironmentRunAllResponseSerializer(serializers.Serializer):
    task = serializers.CharField()


class EnvironmentRunRequestSerializer(serializers.Serializer):
    submission = serializers.IntegerField(required=False, allow_null=True)
    simulate = serializers.BooleanField(required=False, default=True)
    exposedOnly = serializers.BooleanField(required=False, default=False)
    # In practice this may be sent as a JSON-encoded string or a JSON array.
    files = LenientJSONField(required=False)

    def validate_files(self, value):
        if value is None:
            return value
        if not isinstance(value, (list, dict)):
            raise serializers.ValidationError("files must be a JSON array or object")
        return value


class EnvironmentRunResponseSerializer(serializers.Serializer):
    task = serializers.CharField()


class EnvironmentPreviewRequestSerializer(serializers.Serializer):
    language = serializers.CharField(required=False, allow_blank=True)
    buildType = serializers.CharField(required=False, allow_blank=True)
    dockerfile = serializers.CharField(required=False, allow_blank=True)
    dockerRunInstructions = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    requirements = serializers.CharField(required=False, allow_blank=True)


class EnvironmentEjectResponseSerializer(serializers.Serializer):
    dockerfile = serializers.CharField()
    testsJson = serializers.CharField()
    runTestsPy = serializers.CharField()


class EnvironmentRollbackRequestSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)


class EnvironmentRollbackResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    version = serializers.IntegerField()


class EnvironmentCleanupRequestSerializer(serializers.Serializer):
    keep_count = serializers.IntegerField(required=False, default=3)


class EnvironmentCleanupResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    task_id = serializers.CharField()
    message = serializers.CharField()


class EnvironmentConvertToManualRequestSerializer(serializers.Serializer):
    from_version = serializers.IntegerField(required=False)


class EnvironmentConvertToManualResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()


class EnvironmentStatusResponseSerializer(serializers.Serializer):
    environment_id = serializers.IntegerField()
    auto_detect = serializers.BooleanField(required=False)
    current_version = serializers.IntegerField(required=False)
    image_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    build_status = serializers.IntegerField(required=False)
    last_built = serializers.DateTimeField(required=False, allow_null=True)
    successful_runs = serializers.IntegerField(required=False)
    total_runs = serializers.IntegerField(required=False)
    success_rate = serializers.FloatField(required=False)
    convergence_pending = serializers.BooleanField(required=False)
    pending_modules = serializers.ListField(child=serializers.CharField(), required=False)
    version_history = serializers.ListField(child=serializers.DictField(), required=False)
    history_count = serializers.IntegerField(required=False)


