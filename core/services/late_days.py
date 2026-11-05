# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The one late-day rule, shared by analytics and the late-day export.

It mirrors what LateSubmissionHandler actually charges students: days late is
floor(delta / 24h) + 1 for anything past the due date (exactly 24h late is day 2),
except that a first-day submission less than GRACE_PERIOD_HOURS late is on time.
"""
from core.handlers.late_submission_handler import LateSubmissionHandler, date_diff_days, date_diff_hours


def days_late(due, submitted) -> int:
  """Whole late days for a submission uploaded at ``submitted`` against ``due``; 0 if on time."""
  if due is None or submitted is None:
    return 0
  days = date_diff_days(due, submitted)
  if days <= 0:
    return 0
  if days == 1 and date_diff_hours(due, submitted) < LateSubmissionHandler.GRACE_PERIOD_HOURS:
    return 0
  return days
