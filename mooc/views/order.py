from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from core.models import User
from mooc.models import Order
from mooc.serializers.order import OrderPostSerializer, OrderReadSerializer
from mooc.permissions import OrderPermissions

from rest_framework.response import Response
from rest_framework import status

from mooc.stripe_client import StripeClient


class OrderViewSet(viewsets.ModelViewSet):
  queryset = Order.objects.all()
  serializer_class = OrderPostSerializer
  permission_classes = ()
  # permission_classes = (IsAuthenticated, OrderPermissions)

  def create(self, request, *args, **kwargs):
    serializer = self.get_serializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    self.perform_create(serializer)
    headers = self.get_success_headers(serializer.data)

    ############ Create Stripe Checkout Session #############
    user = User.objects.get(email=serializer.data['user'])

    if settings.DEBUG:
      BASE_URL = 'http://localhost:3001/'
    else:
      BASE_URL = 'https://mooc.codepost.io/'

    if user.is_active:
      REDIRECT = 'login'
    else:
      REDIRECT = 'activate'

    success_url = '{BASE_URL}?redirect={REDIRECT}&user={USER}&session_id={{CHECKOUT_SESSION_ID}}'.format(
        BASE_URL=BASE_URL, REDIRECT=REDIRECT, USER=user.email)
    cancel_url = BASE_URL

    order = Order.objects.get(id=serializer.data['id'])
    session = StripeClient().create_checkout_session(order, success_url, cancel_url)
    order.stripeSessionId = session.id
    order.save()

    updated_serializer = OrderReadSerializer(order)

    return Response(updated_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

  def perform_create(self, serializer):
    user = serializer.validated_data['user']
    product = serializer.validated_data['product']
    tier = serializer.validated_data['tier']

    customer_id = StripeClient().get_or_create_customer_id(user)
    userStripeCustomerIdBackup = customer_id

    rateTotal = tier.rateTotal
    rateReview = tier.rateReview

    baseRate = product.cBaseRate
    discountRate = product.cDiscountRate
    reviewRate = product.cReviewRate

    serializer.save(userStripeCustomerIdBackup=userStripeCustomerIdBackup, baseRate=baseRate,
                    discountRate=discountRate, reviewRate=reviewRate, rateTotal=rateTotal, rateReview=rateReview)
