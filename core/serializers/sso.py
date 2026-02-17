from rest_framework import serializers


class CheckSSOAvailabilityResponseSerializer(serializers.Serializer):
    sso_enabled = serializers.BooleanField()
    provider = serializers.CharField(required=False)
    org_id = serializers.IntegerField(required=False)
    org_name = serializers.CharField(required=False)
