# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from drf_spectacular.utils import extend_schema

from core.logging import logEvent
import logging

from core.serializers.emailList import (
    SubscribeToEmailListRequestSerializer,
    SubscribeToEmailListResponseSerializer,
)
logger = logging.getLogger(__name__)


@extend_schema(
    request=SubscribeToEmailListRequestSerializer,
    responses={200: SubscribeToEmailListResponseSerializer}
)
@api_view(['POST'])
def subscribeToEmailList(request):
  if 'email' not in request.data:
    return Response({'success': False}, status=status.HTTP_400_BAD_REQUEST)

  logEvent("Email Subscription", message=f"Email subscription: {request.data['email']}")

  return Response({'success': True}, status=status.HTTP_200_OK)

