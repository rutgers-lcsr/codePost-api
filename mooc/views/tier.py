from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from mooc.models import Tier
from mooc.serializers.product import TierSerializer
from mooc.permissions import TierPermissions

from rest_framework.response import Response
from rest_framework import status


class TierViewSet(viewsets.ModelViewSet):
  queryset = Tier.objects.all()
  serializer_class = TierSerializer
  permission_classes = (TierPermissions,)