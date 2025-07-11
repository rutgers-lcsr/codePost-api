from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Organization

from util.slack import Slack
from core.auth import Authentications, type_of_auth

class OrganizationSerializer(ModelSerializerWithPOSTCheck):
  class Meta:
    model = Organization
    fields = ('id', 'name', 'shortname',)

  def create(self, validated_data):
    user = self.context['request'].user
    token = str(self.context['request'].auth)
    auth_type = type_of_auth(token)

    obj = super().create(validated_data)

    sc = Slack()
    sc.new_instance_notification(obj, user, auth_type)

    return obj