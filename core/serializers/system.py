from rest_framework import serializers


class SystemHealthResponseSerializer(serializers.Serializer):
    database = serializers.CharField()
    celery = serializers.CharField()


class SystemActivityResponseSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField())
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
