# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers


class SystemHealthResponseSerializer(serializers.Serializer):
    database = serializers.CharField()
    celery = serializers.CharField()


class SystemActivityResponseSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField())
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
