from rest_framework import serializers


class ActivateCipResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
