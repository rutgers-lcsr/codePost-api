import functools
import logging
import requests
import json
import time
import socket
from codepost.settings import DEBUG, LOKI_URL
class LokiHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        ts_ns = int(time.time() * 1e9)
        payload = {
            "streams": [
                {
                    "stream": {
                        "app": "django",
                        "level": record.levelname,
                        "host": socket.gethostname(),
                    },
                    "values": [
                        [str(ts_ns), log_entry]
                    ],
                }
            ]
        }
        try:
            requests.post(LOKI_URL, json=payload)
        except Exception as e:
            print("Failed to send log to Loki:", e)

# Attach to logging
loki_handler = LokiHandler()
loki_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(loki_handler)

logger = logging.getLogger("events")


def log_debug(message, *args):
    """
    Log a debug message to Loki.
    :param message: The message to log.
    """
    logger = logging.getLogger(__name__)
    logger.debug(message, *args)


def logEvent(event, level=logging.INFO, message=None):
    """
    Log an event to Loki.
    :param event: The event to log.
    :param level: The logging level (default is INFO).
    """
    try:
        logger = logging.getLogger(__name__)

        full_message = f"[{event}] - {message}" if message else event

        logger.log(
            level,
            msg=
            json.dumps({
            "event": event,
            "message": full_message,
            "level": level,
        }))
    except Exception as e:
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

            

            logger.info(json.dumps({
                "event": event_name or func.__name__,
                "function": func.__name__,
                "user": user.username if user and user.username else "anonymous",
                "path": request.path if hasattr(request, 'path') else None,
                "method": request.method if hasattr(request, 'method') else None,
            }))

            return func(request, *args, **kwargs)
        return wrapper
    return decorator