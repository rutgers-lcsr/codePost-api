import slack
from slack import WebClient as SlackClient
from codepost.settings import DEBUG
from django.conf import settings
from log.models import Event

import json
import time


class Slack:
  api_key = 'xoxb-526958933633-591042355089-afl3CQ8XPrvgXTeVm88hho3H'
  sc = SlackClient(api_key)
  def __init__(self):
    raise NotImplementedError(
        "This class is deprecated. We don't log to Slack anymore. Use logEvent instead.")
  # Documentation on sending beautiful slack messages
  # https://api.slack.com/docs/message-attachments
  def send_message(self, message, attachments=[], blocks=[], channel="#user_notifications", logInDebug=True, debugChannel="#richard-test-2"):
    if settings.TESTING:
      return
    elif not DEBUG:
      self.sc.api_call(
          "chat.postMessage",
          channel=channel,
          text=message,
          attachments=attachments,
          blocks=blocks
      )
    else:
      if (logInDebug):
        self.sc.api_call(
            "chat.postMessage",
            channel=debugChannel,
            text=message,
            attachments=attachments,
            blocks=blocks
        )

  def should_ignore_course(self, course, user):
    ignored_users = ['vinay@codepost.io',
                     'james@codepost.io', 'richard@codepost.io']

    if user.email in ignored_users:
      return True

    return False

  def should_ignore_organization(self, organization, user):
    return False

  def should_ignore_assignment(self, assignment, user):
    return self.should_ignore_course(assignment.course, user)

  def new_instance_notification(self, instance, user, auth_type):
    from core.models import Course, Organization, Assignment
    message = ":boom: New {} created by {} ({})".format(instance.__class__.__name__, user, auth_type)
    fields = [{
        "title": "Object Type",
        "value": instance.__class__.__name__,
        "short": False
    }]

    should_ignore = False
    courseID = 0

    if isinstance(instance, Course):
      should_ignore = self.should_ignore_course(instance, user)
      fields.append({
          "title": "Organization",
          "value": str(instance.organization),
          "short": False
      })
      fields.append({
          "title": "Course",
          "value": str(instance),
          "short": False
      })
      courseID = instance.id
    elif isinstance(instance, Organization):
      should_ignore = self.should_ignore_organization(instance, user)
      fields.append({
          "title": "Organization",
          "value": str(instance),
          "short": False
      })
    elif isinstance(instance, Assignment):
      should_ignore = self.should_ignore_assignment(instance, user)
      fields.append({
          "title": "Assignment",
          "value": str(instance),
          "short": False
      })
      fields.append({
          "title": "Organization",
          "value": str(instance.course.organization),
          "short": False
      })
      fields.append({
          "title": "Course",
          "value": str(instance.course),
          "short": False
      })
      courseID = instance.course.id
    else:
      should_ignore = True

    attachments = json.dumps([
        {
            "color": "#36a64f",
            "fields": fields,
            "ts": time.time()
        }
    ])


    if not should_ignore:
      Event.objects.create(
        category="log",
        user=user.email,
        description="New {}".format(instance.__class__.__name__),
        courseID=courseID,
        meta=json.dumps(attachments)
      )
      self.send_message(message, attachments)
