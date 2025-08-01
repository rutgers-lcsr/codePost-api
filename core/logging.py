import functools
import logging
import requests
import json
import time
import socket
from codepost.settings import DEBUG, LOKI_URL, HOSTNAME
class LokiHandler(logging.Handler):
    def emit(self, record):
        print("LokiHandler emit called")
        ts_ns = int(time.time() * 1e9)
        # Prepare the payload for Loki

        payload = {
            "streams": [
                {
                    "stream": record.msg,
                    "values": [
                        [str(ts_ns)]
                    ],
                }
            ]
        }
        print("LokiHandler payload:", json.dumps(payload, indent=2))
        try:
            requests.post(LOKI_URL, json=payload)
        except Exception as e:
            print("Failed to send log to Loki:", e)

# Attach to logging
loki_handler = LokiHandler()
loki_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(loki_handler)



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
    "CIP Activation",
    "Webhook Error",
    "Webhook Connection Error",
    "API Error",
]


def logEvent(event: str, level=logging.INFO, message: str=None):
    """
    Log an event to Loki.
    :param event: The event to log.
    :param level: The logging level (default is INFO).
    """
    try:
        logger = logging.getLogger(__name__)

        
        if event not in events:
            from core.emails import CodepostAPIErrorEmail

            CodepostAPIErrorEmail().send_email(
                error_message=f"Unknown event logged: {event}",
                error_details=f"An unknown event was logged: {event}"
            )

        message = message or f"Event {event} logged."

        logger.log(
            level,
            msg={
                "event": event,
                "message": message,
                "timestamp": time.time(),
            },
            
        )
    except Exception as e:

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

def log_user_event(event_name):
    def decorator(func):
        from django.contrib.auth.models import User
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            user: User = getattr(request, "user", None)

            logger = logging.getLogger(__name__)

            logger.info(msg= {
                "message": f"User event: {event_name}",
                "event": event_name or func.__name__,
                "function": func.__name__,
                "user": user.username if user and user.username else "anonymous",
                "path": request.path if hasattr(request, 'path') else None,
                "method": request.method if hasattr(request, 'method') else None,
            })

            return func(request, *args, **kwargs)
        return wrapper
    return decorator