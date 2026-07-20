# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Deterministic assignment of per-student dataset variants.

An assignment's dataset pool is the set of AssignmentDataSet rows with
is_student_variant=True. Each student is assigned exactly one (StudentDataSetAssignment),
auto-picked least-loaded-first on first access and cached from then on. Group submissions
share one variant: a student's assignment reuses whatever their current submission's other
members already have, so the whole group sees the same data.
"""
from django.db import IntegrityError, transaction

from core.models import AssignmentDataSet, StudentDataSetAssignment


def get_or_assign(assignment, student):
    """Return the AssignmentDataSet variant assigned to ``student`` for ``assignment``'s
    pool, auto-assigning one if they don't have one yet. Returns None if the assignment has
    no variant pool (is_student_variant datasets)."""
    existing = StudentDataSetAssignment.objects.filter(
        assignment=assignment, student=student).select_related('dataset').first()
    if existing is not None:
        return existing.dataset

    variants = list(AssignmentDataSet.objects.filter(
        assignment=assignment, is_student_variant=True, is_active=True).order_by('id'))
    if not variants:
        return None

    # Group submissions share one variant: if the student's current submission has other
    # members who already have an assignment, reuse it instead of picking a new one.
    current_submission = assignment.submissions.filter(students=student).order_by('-created').first()
    if current_submission is not None:
        groupmate = StudentDataSetAssignment.objects.filter(
            assignment=assignment,
            student__in=current_submission.students.exclude(id=student.id),
        ).select_related('dataset').first()
        if groupmate is not None:
            row, _ = StudentDataSetAssignment.objects.get_or_create(
                assignment=assignment, student=student, defaults={'dataset': groupmate.dataset})
            return row.dataset

    # Least-loaded round-robin over the pool.
    counts = {v.id: 0 for v in variants}
    assigned_dataset_ids = StudentDataSetAssignment.objects.filter(
        assignment=assignment, dataset__in=variants).values_list('dataset_id', flat=True)
    for dataset_id in assigned_dataset_ids:
        counts[dataset_id] = counts.get(dataset_id, 0) + 1
    least_loaded = min(variants, key=lambda v: counts[v.id])

    try:
        with transaction.atomic():
            row = StudentDataSetAssignment.objects.create(
                assignment=assignment, student=student, dataset=least_loaded)
        return row.dataset
    except IntegrityError:
        # Lost the (assignment, student) unique race — someone else just assigned one.
        existing = StudentDataSetAssignment.objects.filter(
            assignment=assignment, student=student).select_related('dataset').first()
        return existing.dataset if existing else None


def get_or_assign_for_submission(assignment, submission):
    """Like ``get_or_assign``, resolved for a submission rather than a single student —
    for callers (the sandbox executor, prompt variables) that have a submission but not a
    specific acting student. Returns None if there's no variant pool or no students."""
    student = submission.students.first() if submission is not None else None
    if student is None:
        return None
    return get_or_assign(assignment, student)
