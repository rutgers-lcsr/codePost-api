from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from mooc.models import Product
from mooc.serializers.product import ProductSerializer
from mooc.permissions import ProductPermissions

from rest_framework.response import Response
from rest_framework import status


class ProductViewSet(viewsets.ModelViewSet):
  queryset = Product.objects.all()
  serializer_class = ProductSerializer
  permission_classes = (ProductPermissions,)
