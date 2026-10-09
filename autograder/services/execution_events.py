# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Recording of autograder execution events for the superadmin stats dashboard.

One row per cache consultation or execution. Recording must never break an
execution, but failures are logged with a traceback rather than swallowed.
"""
import logging

from autograder.services.error_classifier import classify_error

logger = logging.getLogger(__name__)

# Full error output is kept for diagnosis; cap it so a runaway stderr can't
# bloat the table.
MAX_ERROR_DETAIL_LENGTH = 20000


def _current_task_id():
  """Celery task id of the calling task, or '' outside a task context."""
  try:
    from celery import current_task
    request = getattr(current_task, 'request', None)
    task_id = getattr(request, 'id', None)
    return str(task_id)[:64] if task_id else ''
  except Exception:
    return ''


def record_execution_event(*, trigger, cached, success, file=None, assignment=None,
                           submission=None, user=None, language=None, image_name=None,
                           execution_time=None, error_text=None):
  """Persist one AutograderExecutionEvent. Safe to call from any execution path.

  Resolves submission/course/assignment from `file` when not given, and
  snapshots the environment language and image when they are not given.
  """
  try:
    from core.models import AutograderExecutionEvent, Environment

    if file is not None and (assignment is None or submission is None):
      file_submission, file_assignment, _ = file.get_file_info()
      assignment = assignment or file_assignment
      submission = submission or file_submission
    course = assignment.course if assignment is not None else None
    if (language is None or image_name is None) and assignment is not None:
      env = (Environment.objects
             .filter(assignment=assignment)
             .values_list('language', 'image_name')
             .first())
      if env:
        language = env[0] if language is None else language
        image_name = env[1] if image_name is None else image_name

    if not success:
      # classify_error maps empty/None text to ('unknown', '')
      error_category, error_message = classify_error(error_text)
      error_detail = (error_text or '')[:MAX_ERROR_DETAIL_LENGTH]
    else:
      error_category, error_message, error_detail = '', '', ''

    AutograderExecutionEvent.objects.create(
        course=course,
        assignment=assignment,
        submission=submission,
        file=file,
        file_name=(getattr(file, 'name', '') or '')[:250],
        triggered_by=user if getattr(user, 'pk', None) else None,
        trigger=trigger,
        cached=cached,
        success=success,
        language=language or '',
        image_name=image_name or '',
        task_id=_current_task_id(),
        execution_time=execution_time,
        error_category=error_category,
        error_message=error_message,
        error_detail=error_detail,
    )
  except Exception:
    logger.exception("Failed to record autograder execution event")
