# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers


class SubscribeToEmailListRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SubscribeToEmailListResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
