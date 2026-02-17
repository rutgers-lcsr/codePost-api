from rest_framework import serializers


class SubscribeToEmailListRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SubscribeToEmailListResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
