from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from util.slack import Slack
import os

from core.permissions.template import SuperuserPermission
from datetime import datetime

from mooc.models import *


@api_view(['GET'])
@permission_classes([IsAuthenticated, SuperuserPermission])
def datastore_integrity(request):
  slack_client = Slack()

  blocks = [
      {
          "type": "divider"
      },
      {
          "type": "section",
          "text": {
              "type": "mrkdwn",
              "text": "*DATASTORE INTEGRITY CHECK* {}\n_[{}]_".format('' if 'ON_AWS' in os.environ else '[:hammer_and_wrench: LOCAL DATA]', datetime.date(datetime.now()))
          }
      },
      {
          "type": "divider"
      }
  ]

  mooc_courses = list(Product.objects.values_list('course', flat=True))
  credits = Credit.objects.all()
  reviews = Review.objects.all()
  orders = Order.objects.all()

  #####################################################################

  content = ""

  for mooc_course in mooc_courses:
    course = Course.objects.get(id=mooc_course)
    content += str(course) + '\n'

  blocks.append({
      "type": "section",
      "text": {
              "type": "mrkdwn",
              "text": ":zero: MOOC Courses{}".format(content)
      }
  })

  #####################################################################
  #####################################################################

  errors = "\n"

  for mooc_course in mooc_courses:
    course = Course.objects.get(id=mooc_course)

    if not course.noUnfinalize:
      errors += ":x: [noUnfinalize] " + str(course) + '\n'

    if course.minComments < 1:
      errors += ":x: [minComments] " + str(course) + '\n'

    for assignment in course.assignments.all():
      if not assignment.hideGrades:
        errors += ":x: [hideGrades] " + str(course) + "|" + str(assignment) + '\n'

      if not assignment.anonymousGrading:
        errors += ":x: [anonymousGrading] " + str(course) + "|" + str(assignment) + '\n'

      if not assignment.allowStudentUpload:
        errors += ":x: [allowStudentUpload] " + str(course) + "|" + str(assignment) + '\n'

      if not assignment.isReleased:
        errors += ":x: [isReleased] " + str(course) + "|" + str(assignment) + '\n'

      if not assignment.commentFeedback:
        errors += ":x: [commentFeedback] " + str(course) + "|" + str(assignment) + '\n'

      if not assignment.hideGradersFromStudents:
        errors += ":x: [hideGradersFromStudents] " + str(course) + "|" + str(assignment) + '\n'

  if errors == "\n":
    errors = ":white_check_mark:"

  blocks.append({
      "type": "section",
      "text": {
              "type": "mrkdwn",
              "text": ":one: Check Settings of Mooc Courses{}".format(errors)
      }
  })

  #####################################################################
  #####################################################################

  errors = "\n"

  for credit in credits:
    try:
      c = credit.review
    except:
      errors += ":x: " + str(credit) + '\n'

  if errors == "\n":
    errors = ":white_check_mark:"

  blocks.append({
      "type": "section",
      "text": {
              "type": "mrkdwn",
              "text": ":two: Every Credit has a Review{}".format(errors)
      }
  })

  #####################################################################
  #####################################################################

  errors = "\n"

  for review in reviews:
    try:
      r = review.credit
    except:
      errors += ":x: " + str(review) + '\n'

  if errors == "\n":
    errors = ":white_check_mark:"

  blocks.append({
      "type": "section",
      "text": {
              "type": "mrkdwn",
              "text": ":three: Every Review has a Credit{}".format(errors)
      }
  })

  #####################################################################
  #####################################################################

  errors = "\n"

  for credit in credits:
    if credit.stripePaymentIntentId == '':
      errors += ":x: " + str(credit) + '\n'

  if errors == "\n":
    errors = ":white_check_mark:"

  blocks.append({
      "type": "section",
      "text": {
              "type": "mrkdwn",
              "text": ":four: Every Credit has a Stripe Payment Intent{}".format(errors)
      }
  })

  #####################################################################
  #####################################################################

  errors = "\n"

  for order in orders:
    if order.stripeSessionId == '' or order.userStripeCustomerIdBackup == '':
      errors += ":x: " + str(order) + '\n'

  if errors == "\n":
    errors = ":white_check_mark:"

  blocks.append({
      "type": "section",
      "text": {
              "type": "mrkdwn",
              "text": ":five: Every Order has Stripe Data{}".format(errors)
      }
  })

  #####################################################################
  #####################################################################

  errors = "\n"

  for credit in credits:
    user = credit.user
    assignment = credit.assignment

    if assignment != '' and assignment != None:
      related_credits = Credit.objects.filter(user=user, assignment=assignment)

      if related_credits.count() > 1:
        errors += ":x: " + str(credit) + '\n'

  if errors == "\n":
    errors = ":white_check_mark:"

  blocks.append({
      "type": "section",
      "text": {
              "type": "mrkdwn",
              "text": ":six: No User has a duplicate Credits for the same Assignment{}".format(errors)
      }
  })

  #####################################################################
  #####################################################################

  errors = "\n"

  for review in reviews:
    if review.approved:
      try:
        r = review.reviewer
      except:
        errors += ":x: " + str(review) + '\n'

  if errors == "\n":
    errors = ":white_check_mark:"

  blocks.append({
      "type": "section",
      "text": {
              "type": "mrkdwn",
              "text": ":seven: Every Approved Review has a Reviewer{}".format(errors)
      }
  })

  #####################################################################

  slack_client.send_message('Datastore Integrity Check', blocks=blocks, channel="__faas")

  return Response('check', status.HTTP_200_OK)
