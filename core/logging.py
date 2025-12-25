import functools
import logging
import requests
import json
import time
import socket
from codepost.settings import DEBUG, HOSTNAME
from log.models import Event



def log_debug(message, *args):
    """
    Log a debug message to Loki.
    :param message: The message to log.
    """
    logger = logging.getLogger(__name__)
    logger.debug(message, *args)



events = [
    "Core App Ready",
    "Course Created",
    "Organization Created",
    "Assignment Created",
    "Email Subscription",
    "Email Sent",
    "Email Failed",
    "Late Submission Error",
    "Become User",
    "UI Error",
    "User Happiness",
    "User Dump",
    "Admin Change Organization Request",
    "Codepost Registration Error",
    "Admin Already Exists",
    "Admin New Request Error",
    "Admin New Request Denied",
    "Admin New Request Approved",
    "Generate One-Time Token",
    "CIP Activation",
    "Webhook Error",
    "Webhook Connection Error",
    "API Error",
    "One-Time Token Generated"
]


def logEvent(event: str, level=logging.INFO, message: str=None, skip_email: bool=False):
    """
    Log an event to Loki.
    :param event: The event to log.
    :param level: The logging level (default is INFO).
    :param message: The message to log (default is None).
    :param skip_email: Whether to skip sending an email notification (default is False).
    """
    try:
        logger = logging.getLogger(__name__)

        
        if event not in events:
            from core.emails import CodepostAPIErrorEmail
            logger.log(level, "Unknown event logged: {}".format(event))

            if not skip_email:
                CodepostAPIErrorEmail().send_email(
                    error_message=f"Unknown event logged: {event}",
                    error_details=f"An unknown event was logged: {event}"
                )

        message = message or f"Event {event} logged."

        Event.objects.create(category=event, user=None, description=message, courseID=None, meta=json.dumps({
            "event": event,
            "message": message,
            "api-error": 'true',
            "hostname": HOSTNAME,
            "timestamp": time.time(),
            "level": logging.getLevelName(level),
        }))
        logger.log(
            level,
            msg={
                "event": event,
                "message": message,
                "timestamp": time.time(),
            },
        )
    except Exception as e:
        if skip_email:
            return
        # check if E is failed to send email
        if "Failed to send email" in str(e):
            print(f"Failed to log event {event}: {e}")
            return

        # If logging to loki fails, that means something is wrong with the Loki server or network.
        # We should log this error to the console and send an email notification to the admin.
        if not DEBUG:
            print(f"Failed to log event {event}: {e}")
            # Send an email notification if logging fails
            from core.emails import CodepostAPIErrorEmail
            CodepostAPIErrorEmail().send_email(
                error_message=f"Failed to log event {event}",
                error_details=f"An error occurred while logging event {event}: {str(e)}"
            )