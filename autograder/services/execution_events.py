# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Recording of autograder execution events for the superadmin stats dashboard.

One row per cache consultation or execution. Recording must never break an
execution, but failures are logged with a traceback rather than swallowed.
"""
import logging

from autograder.services.error_classifier import classify_error

logger = logging.getLogger(__name__)


def record_execution_event(*, trigger, cached, success, file=None, assignment=None,
                           language=None, error_text=None):
  """Persist one AutograderExecutionEvent. Safe to call from any execution path.

  Resolves course/assignment from `file` when `assignment` is not given, and
  snapshots the environment language when `language` is not given.
  """
  try:
    from core.models import AutograderExecutionEvent, Environment

    if assignment is None and file is not None:
      _, assignment, _ = file.get_file_info()
    course = assignment.course if assignment is not None else None
    if language is None and assignment is not None:
      language = (Environment.objects
                  .filter(assignment=assignment)
                  .values_list('language', flat=True)
                  .first()) or ''

    if not success:
      # classify_error maps empty/None text to ('unknown', '')
      error_category, error_message = classify_error(error_text)
    else:
      error_category, error_message = '', ''

    AutograderExecutionEvent.objects.create(
        course=course,
        assignment=assignment,
        trigger=trigger,
        cached=cached,
        success=success,
        language=language or '',
        error_category=error_category,
        error_message=error_message,
    )
  except Exception:
    logger.exception("Failed to record autograder execution event")
