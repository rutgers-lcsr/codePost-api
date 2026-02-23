# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Course
from webhooks.models import Hook

class WebhookSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = Hook
    fields = ('id', 'course', 'event', 'target', 'is_active', 'last_triggered_at', 'last_triggered_status')
    POST_permissions_fields = ('course',)
    read_only_fields = ('last_triggered_at', 'last_triggered_status')

