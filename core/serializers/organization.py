# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.logging import logEvent
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Organization, User

from core.auth import type_of_auth
import logging

logger = logging.getLogger(__name__)


class OrganizationSerializer(ModelSerializerWithPOSTCheck):
  emailDomain = serializers.CharField(source="email_domain", required=False, allow_null=True)
  allowedEmailDomains = serializers.ListField(
      child=serializers.CharField(), source="allowed_email_domains", required=False, default=list
  )
  ssoEnabled = serializers.BooleanField(source="sso_enabled", required=False)
  ssoProvider = serializers.CharField(source="sso_provider", required=False, allow_null=True)
  ssoConfig = serializers.JSONField(source="sso_config", required=False, allow_null=True)
  sendWelcomeEmail = serializers.BooleanField(source="send_welcome_email", required=False)

  # Expected keys per SSO provider for sso_config validation
  SSO_CONFIG_KEYS = {
    'CAS': {'cas_server_url', 'cas_version'},
    'AZURE': {'tenant_id', 'client_id', 'client_secret'},
    'OIDC': {'discovery_url', 'client_id', 'client_secret'},
    'GOOGLE': {'client_id', 'client_secret', 'hosted_domain'},
  }

  SSO_CONFIG_REQUIRED_KEYS = {
    'CAS': {'cas_server_url'},
    'AZURE': {'tenant_id', 'client_id', 'client_secret'},
    'OIDC': {'discovery_url', 'client_id', 'client_secret'},
    'GOOGLE': {'client_id', 'client_secret'},
  }

  class Meta:
    model = Organization
    fields = ('id', 'name', 'shortname', 'emailDomain', 'allowedEmailDomains', 'ssoEnabled', 'ssoProvider', 'ssoConfig', 'sendWelcomeEmail')

  def validate(self, attrs):
    sso_config = attrs.get('sso_config')
    sso_provider = attrs.get('sso_provider', getattr(self.instance, 'sso_provider', None))
    sso_enabled = attrs.get('sso_enabled', getattr(self.instance, 'sso_enabled', False))

    if sso_config and isinstance(sso_config, dict) and sso_provider:
      allowed_keys = self.SSO_CONFIG_KEYS.get(sso_provider, set())
      unexpected_keys = set(sso_config.keys()) - allowed_keys
      if unexpected_keys:
        raise serializers.ValidationError({
          'ssoConfig': f"Unexpected keys for {sso_provider} provider: {', '.join(sorted(unexpected_keys))}. "
                       f"Allowed keys: {', '.join(sorted(allowed_keys))}"
        })

      if sso_enabled:
        required_keys = self.SSO_CONFIG_REQUIRED_KEYS.get(sso_provider, set())
        missing_keys = required_keys - set(sso_config.keys())
        if missing_keys:
          raise serializers.ValidationError({
            'ssoConfig': f"Missing required keys for {sso_provider} provider: {', '.join(sorted(missing_keys))}"
          })

    return attrs

  def create(self, validated_data):
    user: User = self.context['request'].user
    token = str(self.context['request'].auth)
    auth_type = type_of_auth(token)

    obj: Organization = super().create(validated_data)

    logEvent("Organization Created",
             message=f"Organization {obj.name} created by {user.email} with auth type {auth_type}")


    return obj