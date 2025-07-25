from rest_framework import serializers
from core.logging import logEvent
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Organization, User

from util.slack import Slack
from core.auth import Authentications, type_of_auth
import logging

logger = logging.getLogger(__name__)


class OrganizationSerializer(ModelSerializerWithPOSTCheck):
  class Meta:
    model = Organization
    fields = ('id', 'name', 'shortname',)

  def create(self, validated_data):
    user: User = self.context['request'].user
    token = str(self.context['request'].auth)
    auth_type = type_of_auth(token)

    obj: Organization = super().create(validated_data)

    logEvent("Organization Created",
             message=f"Organization {obj.name} created by {user.email} with auth type {auth_type}")
    # sc = Slack()
    # sc.new_instance_notification(obj, user, auth_type)

    return obj