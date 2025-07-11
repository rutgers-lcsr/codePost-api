from django.urls import path, re_path, include

from mooc.views.fulfillment import fulfillment_webhook
from mooc.views.notifications import notification_webhook
from mooc.views.su import datastore_integrity
from mooc.views.product import ProductViewSet
from mooc.views.order import OrderViewSet
from mooc.views.credit import CreditViewSet
from mooc.views.review import ReviewViewSet
from mooc.views.payout import PayoutViewSet
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'credits', CreditViewSet)
router.register(r'reviews', ReviewViewSet)
router.register(r'payouts', PayoutViewSet)

urlpatterns = [
    path('fulfillment_webhook/', fulfillment_webhook),
    path('notification_webhook/', notification_webhook),
    path('datastore_integrity/', datastore_integrity),
    re_path('', include(router.urls)),
]
