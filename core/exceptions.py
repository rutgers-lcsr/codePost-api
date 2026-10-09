# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Error responses the SPA can read.

DRF only translates its own APIException family; anything else escapes as Django's
HTML "Server Error (500)" / "Bad Request (400)" page, which the client cannot tell
apart from any other failure. The handler below maps the exception classes that
user input can trigger onto JSON responses with a `detail` string — the shape the
SPA's apiErrorMessage reads — and the handler_* views do the same for errors that
never reach a DRF view (unknown routes, crashes in plain Django views).

Everything still goes to the log: a 404 for a DoesNotExist a view should have
guarded is logged at WARNING with the traceback so the bug stays visible.
"""
import logging

from django.core.exceptions import (
    ObjectDoesNotExist, RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent,
    ValidationError as DjangoValidationError,
)
from django.db import IntegrityError
from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from core.constants import MAX_REQUEST_BODY_BYTES

logger = logging.getLogger(__name__)

UPLOAD_TOO_LARGE_DETAIL = (
    f"Upload too large: a single request may not exceed "
    f"{MAX_REQUEST_BODY_BYTES // (1024 * 1024)} MB."
)
TOO_MANY_FILES_DETAIL = "Too many files in one request. Upload them in smaller batches."
TOO_MANY_FIELDS_DETAIL = "Too many form fields in one request."
CONFLICT_DETAIL = "That conflicts with an existing record (a name or key is already in use)."
NOT_FOUND_DETAIL = "The object you requested could not be found."
SERVER_ERROR_DETAIL = "Something went wrong on the server. The codePost team has been notified."


def _django_validation_payload(exc: DjangoValidationError) -> dict:
    """Model/validator ValidationError → DRF-style body: field errors when the error
    is keyed by field, otherwise a single `detail`."""
    if hasattr(exc, 'error_dict'):
        payload: dict = {field: [str(m) for m in messages] for field, messages in exc.message_dict.items()}
        first = next(iter(payload.values()), [])
        payload['detail'] = first[0] if first else 'Invalid input.'
        return payload
    messages = [str(m) for m in exc.messages]
    return {'detail': ' '.join(messages) if messages else 'Invalid input.'}


def exception_handler(exc, context):
    if isinstance(exc, RequestDataTooBig):
        return Response({"detail": UPLOAD_TOO_LARGE_DETAIL}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if isinstance(exc, TooManyFilesSent):
        return Response({"detail": TOO_MANY_FILES_DETAIL}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, TooManyFieldsSent):
        return Response({"detail": TOO_MANY_FIELDS_DETAIL}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, DjangoValidationError):
        return Response(_django_validation_payload(exc), status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, IntegrityError):
        _log_translated(exc, context)
        return Response({"detail": CONFLICT_DETAIL}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, ObjectDoesNotExist):
        _log_translated(exc, context)
        return Response({"detail": NOT_FOUND_DETAIL}, status=status.HTTP_404_NOT_FOUND)
    return drf_exception_handler(exc, context)


def _log_translated(exc, context):
    request = context.get('request') if context else None
    where = f"{request.method} {request.path}" if request is not None else "?"
    logger.warning("translated %s during %s: %s", type(exc).__name__, where, exc, exc_info=exc)


# --- Django-level handlers (errors that never reach a DRF view) -----------------

def handler_400(request, exception=None):
    detail = str(exception) if isinstance(exception, DjangoValidationError) else "Bad request."
    return JsonResponse({"detail": detail}, status=400)


def handler_403(request, exception=None):
    return JsonResponse({"detail": "You do not have permission to perform this action."}, status=403)


def handler_404(request, exception=None):
    return JsonResponse({"detail": f"No endpoint at {request.path}."}, status=404)


def handler_500(request):
    return JsonResponse({"detail": SERVER_ERROR_DETAIL}, status=500)
