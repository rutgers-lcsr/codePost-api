from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from core.auth import Authentications, type_of_auth
from log.models import Event

from util.slack import Slack

import json

##########################################################################
#####################################      Logging      ##################
#####################################                   ##################
##########################################################################


@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def logError(request):
  """
  Request body includes: error, errorInfo.

  Notifies codePost Slack of any uncaught UI errors. Initiated via globally-scoped
  ErrorBoundary on the frontend. https://reactjs.org/docs/error-boundaries.html

  """
  user = request.user
  error = request.data['error'] if 'error' in request.data else ''
  errorDetail = request.data[
      'errorDetail'] if 'errorDetail' in request.data else ''
  url = request.data['url'] if 'url' in request.data else ''

  fullstory = "https://app.fullstory.com/ui/MFFNS/segments/everyone/people:search:((NOW%2FDAY-29DAY:NOW%2FDAY%2B1DAY):((UserEmail:==:%22{}%22)):():():():)/0".format(
      user)

  loginas = "https://codepost.io/loginas/{}".format(user)

  message = ":warning: User error ({user} | {url} | <{fullstory}|Find on Fullstory> | <{loginas}|Login>)\n>>>*{error}*\n{errorDetail}".format(
      user=user, url=url, fullstory=fullstory, error=error, errorDetail=errorDetail, loginas=loginas)


  try:
    meta = {
      url: url,
      error: error,
      errorDetail: errorDetail
    }
    Event.objects.create(category="error", user=user.email, description="User Error: {}".format(error), meta=json.dumps(meta))
  except:
    pass

  sc = Slack()
  sc.send_message(message, attachments=[], channel="#user_errors")
  return Response({'success': True}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def logHappiness(request):
  """
  Notifies codePost Slack of any happiness occurring on the frontend (by authenticated users).

  """
  user = request.user
  message = request.data['message'] if 'message' in request.data else ''
  url = request.data['url'] if 'url' in request.data else ''

  attachments = [
      {
          "title": message,
          "title_link": url,
          "footer": str(user),
      }
  ]

  sc = Slack()
  sc.send_message('', attachments=attachments)
  return Response({'success': True}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def logDump(request):

  ignored_users = ['vinay@codepost.io', 'james@codepost.io', 'richard@codepost.io']

  if request.user.email in ignored_users:
    return Response({'success': True}, status=status.HTTP_200_OK)

  sc = Slack()
  channel = request.data['channel'] if request.data['channel'] else "#user_notifications_everything"

  attachments = []
  heading = str(request.user)
  if request.data['attachments']:
    attachments = request.data['attachments']
    if len(attachments) > 0 and attachments[0]['title']:
      heading = "{} | {}".format(attachments[0]['title'], str(request.user))

  description = heading.split('|')[0].strip()
  courseID = request.data.get('courseID', 0)

  Event.objects.create(category="log", user=request.user.email, description=description, courseID=courseID, meta=json.dumps(attachments))

  sc.send_message(heading, attachments=attachments, channel=channel, logInDebug=True)
  return Response({'success': True}, status=status.HTTP_200_OK)
