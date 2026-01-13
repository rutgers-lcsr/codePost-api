import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from core.auth import Authentications, type_of_auth
from core.logging import logEvent
from log.models import Event
from codepost.settings import DEBUG

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

  Notifies codePost of any uncaught UI errors. Initiated via globally-scoped
  ErrorBoundary on the frontend. https://reactjs.org/docs/error-boundaries.html

  """
  user = request.user
  error = request.data['error'] if 'error' in request.data else ''
  errorDetail = request.data[
      'errorDetail'] if 'errorDetail' in request.data else ''
  url = request.data['url'] if 'url' in request.data else ''

  fullstory = "https://app.fullstory.com/ui/MFFNS/segments/everyone/people:search:((NOW%2FDAY-29DAY:NOW%2FDAY%2B1DAY):((UserEmail:==:%22{}%22)):():():():)/0".format(
      user)

  loginas = "{}/loginAs?email={}".format(settings.CLIENT_URL, user)

  message = ":warning: User error ({user} | {url} | <{loginas}|Login>)\n>>>*{error}*\n{errorDetail}".format(
      user=user, url=url, fullstory=fullstory, error=error, errorDetail=errorDetail, loginas=loginas)


  try:
    meta = {
      "url": url,
      "error": error,
      "errorDetail": errorDetail,
      "message": message,
    }
    if DEBUG:
      logging.warning(meta)

    Event.objects.create(category="UI Error", user=user.email, description="User Error: {}".format(error), meta=json.dumps(meta))
  except:
    pass
  return Response({'success': True}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def logHappiness(request):
  """
  Notifies codePost of any happiness occurring on the frontend (by authenticated users).

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
  Event.objects.create(category="User Happiness", user=user.email, description=message, meta=json.dumps(attachments))
  return Response({'success': True}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def logDump(request):

  ignored_users = ['vinay@codepost.io', 'james@codepost.io', 'richard@codepost.io']

  if request.user.email in ignored_users:
    return Response({'success': True}, status=status.HTTP_200_OK)

  attachments = []
  heading = str(request.user)
  if request.data['attachments']:
    attachments = request.data['attachments']
    if len(attachments) > 0 and attachments[0]['title']:
      heading = "{} | {}".format(attachments[0]['title'], str(request.user))

  description = heading.split('|')[0].strip()
  courseID = request.data.get('courseID', 0)

  Event.objects.create(category="User Dump", user=request.user.email, description=description, courseID=courseID, meta=json.dumps(attachments))

  return Response({'success': True}, status=status.HTTP_200_OK)


