# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
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


class ExchangeOTTRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class ExchangeOTTResponseSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="Short-lived access token.")
    refresh = serializers.CharField(help_text="Rotating refresh token.")


class ImpersonateRequestSerializer(serializers.Serializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    never_expire = serializers.BooleanField(required=False, default=False)


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="The refresh token to blacklist.")


class LogoutResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
