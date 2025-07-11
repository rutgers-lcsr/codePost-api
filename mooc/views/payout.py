from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from mooc.models import Payout, Review
from mooc.serializers.payout import PayoutSerializer, PayoutPostSerializer
from mooc.permissions import PayoutPermissions

from rest_framework.response import Response
from rest_framework import status
from rest_framework import serializers


class PayoutViewSet(viewsets.ModelViewSet):
  queryset = Payout.objects.all()
  serializer_class = PayoutSerializer
  permission_classes = (IsAuthenticated, PayoutPermissions)

  def get_serializer_class(self):
    if self.action == 'create':
      return PayoutPostSerializer
    else:
      return PayoutSerializer

  def list(self, request, *args, **kwargs):
    queryset = Payout.objects.filter(reviewer=self.request.user)

    serializer = PayoutSerializer(queryset, many=True)
    return Response(serializer.data)

  def create(self, request, *args, **kwargs):
    serializer = self.get_serializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    self.perform_create(serializer)

    # Query for reviews that...
    # - belong to this user
    # - have been approved by an admin
    # - do not have an associated payout yet
    reviews = Review.objects.filter(reviewer__username=serializer.data['reviewer'], approved=True, payout=None)
    payout = Payout.objects.get(id=serializer.data['id'])

    for review in reviews:
      review.payout = payout
      review.save()

    headers = self.get_success_headers(serializer.data)
    return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

  def perform_create(self, serializer):
    reviewer = self.request.user
    reviews = Review.objects.filter(reviewer__username=reviewer, approved=True, payout=None)

    total = 0
    for review in reviews.all():
      total += review.rateReview

    PAYOUT_MINIMUM = 2000

    if total < PAYOUT_MINIMUM:
      raise serializers.ValidationError("You do not have enough eligible balance for payout yet.")

    serializer.save(reviewer=reviewer)
