# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers


class GenerateOTTRequestSerializer(serializers.Serializer):
    username = serializers.CharField()


class GenerateOTTResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    expires_at = serializers.DateTimeField()


class ValidateOTTRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class JwtOttResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    expires_at = serializers.IntegerField()
