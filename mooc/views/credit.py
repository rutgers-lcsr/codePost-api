from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from mooc.models import Credit
from mooc.serializers.credit import CreditSerializer
from mooc.permissions import CreditPermissions

from rest_framework.response import Response
from rest_framework import status


class CreditViewSet(viewsets.ModelViewSet):
  queryset = Credit.objects.all()
  serializer_class = CreditSerializer
  permission_classes = (IsAuthenticated, CreditPermissions)

  def list(self, request, *args, **kwargs):
    queryset = Credit.objects.filter(user=self.request.user)

    serializer = CreditSerializer(queryset, many=True)
    return Response(serializer.data)
