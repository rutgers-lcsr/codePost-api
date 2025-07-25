from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view

from util.slack import Slack


@api_view(['POST'])
def subscribeToEmailList(request):
  if 'email' not in request.data:
    return Response({'success': False}, status=status.status.HTTP_400_BAD_REQUEST)

  # sc = Slack()
  # message = "{} subscribed to the product updates email list!".format(request.data['email'])
  # channel = '#email-list-subscribers'
  # debugChannel = '#richard-test-2'
  # sc.send_message(message, channel=channel, logInDebug=True, debugChannel=debugChannel)

  return Response({'success': True}, status=status.HTTP_200_OK)
