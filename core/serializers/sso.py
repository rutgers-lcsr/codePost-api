# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers


class CheckSSOAvailabilityResponseSerializer(serializers.Serializer):
    sso_enabled = serializers.BooleanField()
    provider = serializers.CharField(required=False)
    org_id = serializers.IntegerField(required=False)
    org_name = serializers.CharField(required=False)
