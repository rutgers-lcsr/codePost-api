from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view

from core.logging import logEvent
from util.slack import Slack
import logging
logger = logging.getLogger(__name__)


@api_view(['POST'])
def subscribeToEmailList(request):
  if 'email' not in request.data:
    return Response({'success': False}, status=status.status.HTTP_400_BAD_REQUEST)


  # sc = Slack()
  # message = "{} subscribed to the product updates email list!".format(request.data['email'])
  # channel = '#email-list-subscribers'
  # debugChannel = '#richard-test-2'
  # sc.send_message(message, channel=channel, logInDebug=True, debugChannel=debugChannel)

  logEvent("Email subscription", message=f"Email subscription: {request.data['email']}")

  return Response({'success': True}, status=status.HTTP_200_OK)
