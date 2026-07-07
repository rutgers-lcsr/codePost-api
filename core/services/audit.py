# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Centralized audit event recording for course activity tracking.
"""
import logging
from datetime import timedelta
from django.utils.timezone import now

from core.models import CourseAuditEvent

logger = logging.getLogger(__name__)

# Event types that should be deduplicated within a time window
_DEDUP_EVENT_TYPES = {'file_view', 'feedback_view'}
_DEDUP_WINDOW = timedelta(minutes=5)


def record_audit_event(course, event_type, user=None, assignment=None, submission=None, quiz=None, meta=None):
    """
    Record a course audit event.

    For file_view and feedback_view events, deduplicates within a 5-minute window
    per user/submission to avoid spam from page refreshes.

    Args:
        course: Course instance
        event_type: One of the CourseAuditEvent.EVENT_TYPE_CHOICES values
        user: User instance (the actor, typically a student)
        assignment: Assignment instance (optional)
        submission: Submission instance (optional)
        quiz: Quiz instance (optional)
        meta: dict of extra context (optional)
    """
    if event_type in _DEDUP_EVENT_TYPES and user and submission:
        cutoff = now() - _DEDUP_WINDOW
        exists = CourseAuditEvent.objects.filter(
            course=course,
            event_type=event_type,
            user=user,
            submission=submission,
            created__gte=cutoff,
        ).exists()
        if exists:
            return None

    try:
        return CourseAuditEvent.objects.create(
            course=course,
            event_type=event_type,
            user=user,
            assignment=assignment,
            submission=submission,
            quiz=quiz,
            meta=meta,
        )
    except Exception:
        logger.exception("Failed to record audit event: %s", event_type)
        return None
