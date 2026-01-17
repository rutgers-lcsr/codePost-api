from rest_framework import status, serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.decorators import api_view
from drf_spectacular.utils import extend_schema, inline_serializer

from core.logging import logEvent
import logging
logger = logging.getLogger(__name__)


@extend_schema(
    request=inline_serializer(
        name='SubscribeToEmailListRequest',
        fields={'email': drf_serializers.EmailField()}
    ),
    responses={
        200: inline_serializer(
            name='SubscribeToEmailListResponse',
            fields={'success': drf_serializers.BooleanField()}
        ),
    }
)
@api_view(['POST'])
def subscribeToEmailList(request):
  if 'email' not in request.data:
    return Response({'success': False}, status=status.HTTP_400_BAD_REQUEST)

  logEvent("Email Subscription", message=f"Email subscription: {request.data['email']}")

  return Response({'success': True}, status=status.HTTP_200_OK)

