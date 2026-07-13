# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers


class LogErrorRequestSerializer(serializers.Serializer):
    error = serializers.CharField(required=False, allow_blank=True)
    errorDetail = serializers.CharField(required=False, allow_blank=True)
    url = serializers.CharField(required=False, allow_blank=True)
    screenshot = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, default='UI Error')


class LogHappinessRequestSerializer(serializers.Serializer):
    message = serializers.CharField(required=False, allow_blank=True)
    url = serializers.CharField(required=False, allow_blank=True)


class LogDumpRequestSerializer(serializers.Serializer):
    attachments = serializers.ListField(child=serializers.DictField(), required=False)
    courseID = serializers.IntegerField(required=False)


class LogSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
