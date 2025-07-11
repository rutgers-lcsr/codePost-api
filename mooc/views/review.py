from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from mooc.models import Review
from mooc.serializers.review import ReviewSerializer
from mooc.permissions import ReviewPermissions

from rest_framework.response import Response
from rest_framework import status


class ReviewViewSet(viewsets.ModelViewSet):
  queryset = Review.objects.all()
  serializer_class = ReviewSerializer
  permission_classes = (IsAuthenticated, ReviewPermissions)

  def list(self, request, *args, **kwargs):
    queryset = Review.objects.filter(reviewer=self.request.user)

    serializer = ReviewSerializer(queryset, many=True)
    return Response(serializer.data)
