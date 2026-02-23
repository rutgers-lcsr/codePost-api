# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.logging import logEvent
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Organization, User

from core.auth import Authentications, type_of_auth
import logging

logger = logging.getLogger(__name__)


class OrganizationSerializer(ModelSerializerWithPOSTCheck):
  emailDomain = serializers.CharField(source="email_domain", required=False, allow_null=True)
  sso_config = serializers.JSONField(required=False, allow_null=True)

  class Meta:
    model = Organization
    fields = ('id', 'name', 'shortname', 'emailDomain', 'sso_enabled', 'sso_provider', 'sso_config', 'send_welcome_email')

  def create(self, validated_data):
    user: User = self.context['request'].user
    token = str(self.context['request'].auth)
    auth_type = type_of_auth(token)

    obj: Organization = super().create(validated_data)

    logEvent("Organization Created",
             message=f"Organization {obj.name} created by {user.email} with auth type {auth_type}")


    return obj