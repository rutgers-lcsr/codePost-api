# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Deterministic assignment of per-student dataset variants.

An assignment's dataset pool is the set of AssignmentDataSet rows with
is_student_variant=True. Each student is assigned exactly one (StudentDataSetAssignment),
auto-picked least-loaded-first on first access and cached from then on. Group submissions
share one variant: a student's assignment reuses whatever their current submission's other
members already have, so the whole group sees the same data.
"""
import logging

from django.db import IntegrityError, transaction

from core.models import AssignmentDataSet, StudentDataSetAssignment

logger = logging.getLogger(__name__)


def _groupmate_variant(assignment, student):
    """The variant a group submission's other members already hold, so the whole group sees
    the same data. Returns None if the student has no current submission or no groupmate has
    one yet. If groupmates disagree (a staff override or a regroup), logs a warning and picks
    the earliest-created assignment deterministically instead of an arbitrary one."""
    current_submission = assignment.submissions.filter(
        students=student).order_by('-created').first()
    if current_submission is None:
        return None
    groupmate_rows = list(StudentDataSetAssignment.objects.filter(
        assignment=assignment,
        student__in=current_submission.students.exclude(id=student.id),
    ).select_related('dataset').order_by('created'))
    if not groupmate_rows:
        return None
    if len({r.dataset_id for r in groupmate_rows}) > 1:
        logger.warning(
            "Group members hold multiple different dataset variants for assignment %s "
            "(submission %s); assigning student %s the earliest-created one.",
            assignment.id, current_submission.id, student.id)
    return groupmate_rows[0].dataset


def get_or_assign(assignment, student):
    """Return the AssignmentDataSet variant assigned to ``student`` for ``assignment``'s
    pool, auto-assigning one if they don't have one yet. Returns None if the assignment has
    no variant pool (is_student_variant datasets)."""
    # Fast path: already assigned. The row never changes once created, so no lock needed.
    existing = StudentDataSetAssignment.objects.filter(
        assignment=assignment, student=student).select_related('dataset').first()
    if existing is not None:
        return existing.dataset

    # Cheap pool check before taking the lock below.
    if not AssignmentDataSet.objects.filter(
            assignment=assignment, is_student_variant=True, is_active=True).exists():
        return None

    try:
        with transaction.atomic():
            # Serialize concurrent first-access for this assignment so the least-loaded
            # count can't race two students onto the same variant. select_for_update locks
            # the pool rows — a real row lock on MySQL (prod), a harmless no-op under
            # SQLite's whole-DB locking (dev/test). Ordered by id for a stable lock order.
            variants = list(AssignmentDataSet.objects.select_for_update().filter(
                assignment=assignment, is_student_variant=True,
                is_active=True).order_by('id'))
            if not variants:
                return None

            # Re-check inside the lock: a peer may have assigned while we waited for it.
            existing = StudentDataSetAssignment.objects.filter(
                assignment=assignment, student=student).select_related('dataset').first()
            if existing is not None:
                return existing.dataset

            # Group submissions share one variant; otherwise least-loaded round-robin.
            chosen = _groupmate_variant(assignment, student)
            if chosen is None:
                counts = {v.id: 0 for v in variants}
                for dataset_id in StudentDataSetAssignment.objects.filter(
                        assignment=assignment, dataset__in=variants
                        ).values_list('dataset_id', flat=True):
                    counts[dataset_id] = counts.get(dataset_id, 0) + 1
                chosen = min(variants, key=lambda v: counts[v.id])

            row = StudentDataSetAssignment.objects.create(
                assignment=assignment, student=student, dataset=chosen)
        return row.dataset
    except IntegrityError:
        # Lost the (assignment, student) unique race — under SQLite select_for_update doesn't
        # truly serialize, so a concurrent assigner can still slip in. Re-fetch theirs.
        existing = StudentDataSetAssignment.objects.filter(
            assignment=assignment, student=student).select_related('dataset').first()
        return existing.dataset if existing else None


def random_variant(assignment):
    """A random active pool variant WITHOUT persisting an assignment row — for prompt
    test previews seeded from instructor demo files rather than a real student."""
    return AssignmentDataSet.objects.filter(
        assignment=assignment, is_student_variant=True, is_active=True).order_by('?').first()


def get_or_assign_for_submission(assignment, submission):
    """Like ``get_or_assign``, resolved for a submission rather than a single student —
    for callers (the sandbox executor, prompt variables) that have a submission but not a
    specific acting student. Returns None if there's no variant pool or no students."""
    student = submission.students.first() if submission is not None else None
    if student is None:
        return None
    return get_or_assign(assignment, student)
