from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view

from core.logging import logEvent
import logging
logger = logging.getLogger(__name__)


@api_view(['POST'])
def subscribeToEmailList(request):
  if 'email' not in request.data:
    return Response({'success': False}, status=status.HTTP_400_BAD_REQUEST)

  logEvent("Email Subscription", message=f"Email subscription: {request.data['email']}")

  return Response({'success': True}, status=status.HTTP_200_OK)
