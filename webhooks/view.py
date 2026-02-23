# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from webhooks.models import Hook
from webhooks.serializer import WebhookSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from webhooks.permissions import WebhookPermissions

class WebhookViewSet(ListProtectedViewSet):
  queryset = Hook.objects.all()
  serializer_class = WebhookSerializer
  permission_classes = (IsAuthenticated, WebhookPermissions)