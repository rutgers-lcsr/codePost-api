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
