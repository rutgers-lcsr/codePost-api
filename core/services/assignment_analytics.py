# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Assignment Analytics Service

Provides aggregated analytics for assignment-level insights:
grade distribution, grader workload, grading timeline, and test results summary.
"""

import math
from collections import Counter

from django.db.models import Count, F, Q
from django.db.models.functions import TruncDay

from core.models import Assignment, Submission, SubmissionTest


def get_grade_distribution(assignment: Assignment, num_buckets: int = 10) -> list[dict]:
    """
    Bucket finalized submission grades into ranges.
    Returns list of {bucketMin, bucketMax, count}.
    """
    points = float(assignment.points)
    if points <= 0:
        return []

    num_buckets = max(1, min(num_buckets, 100))
    bucket_size = points / num_buckets

    submissions = Submission.objects.filter(
        assignment=assignment,
        isFinalized=True,
    ).exclude(grade=None)

    if not submissions.exists():
        return []

    num_buckets = math.ceil(points / bucket_size)

    # Compute bucket index in Python to avoid DB-engine-specific type issues
    grades = submissions.values_list('grade', flat=True)
    bucket_counts: Counter[int] = Counter()
    for grade in grades:
        idx = min(int(float(grade) // bucket_size), num_buckets - 1)
        bucket_counts[idx] += 1

    distribution = []
    for i in range(num_buckets):
        bucket_min = round(i * bucket_size, 2)
        bucket_max = round(min((i + 1) * bucket_size, points), 2)
        count = bucket_counts.get(i, 0)
        distribution.append({
            'bucketMin': bucket_min,
            'bucketMax': bucket_max,
            'count': count,
        })

    return distribution


def get_grader_workload(assignment: Assignment) -> list[dict]:
    """
    Group submissions by grader and count finalized/unfinalized.
    Returns list of {grader, finalized, unfinalized, total}.
    """
    results = (
        Submission.objects.filter(assignment=assignment)
        .exclude(grader=None)
        .values(grader_email=F('grader__email'))
        .annotate(
            finalized=Count('id', filter=Q(isFinalized=True)),
            unfinalized=Count('id', filter=Q(isFinalized=False)),
            total=Count('id'),
        )
        .order_by('-total')
    )

    return [
        {
            'grader': r['grader_email'],
            'finalized': r['finalized'],
            'unfinalized': r['unfinalized'],
            'total': r['total'],
        }
        for r in results
    ]


def get_grading_timeline(assignment: Assignment) -> list[dict]:
    """
    Count finalized submissions per day (using `modified` as proxy for finalization time).
    Returns list of {period, count} ordered chronologically.
    """
    results = (
        Submission.objects.filter(
            assignment=assignment,
            isFinalized=True,
        )
        .annotate(period=TruncDay('modified'))
        .values('period')
        .annotate(count=Count('id'))
        .order_by('period')
    )

    return [
        {
            'period': r['period'].isoformat(),
            'count': r['count'],
        }
        for r in results
    ]


def get_test_results_summary(assignment: Assignment) -> list[dict]:
    """
    Aggregate pass/fail/error counts per test case across all submissions.
    Returns list of {testCaseDescription, testCategoryName, passed, failed, errored, total}.
    """
    test_results = (
        SubmissionTest.objects.filter(submission__assignment=assignment)
        .select_related('testCase', 'testCase__testCategory')
        .values_list(
            'testCase__id',
            'testCase__description',
            'testCase__testCategory__name',
            'testCase__sortKey',
            'passed',
            'isError',
        )
    )

    # Aggregate in Python to avoid SQLite conditional-Count issues
    stats: dict[int, dict] = {}
    for tc_id, tc_desc, cat_name, sort_key, passed, is_error in test_results:
        if tc_id not in stats:
            stats[tc_id] = {
                'testCaseDescription': tc_desc,
                'testCategoryName': cat_name,
                'sortKey': sort_key or 0,
                'passed': 0,
                'failed': 0,
                'errored': 0,
                'total': 0,
            }
        entry = stats[tc_id]
        entry['total'] += 1
        if is_error:
            entry['errored'] += 1
        elif passed:
            entry['passed'] += 1
        else:
            entry['failed'] += 1

    # Sort by category name then sort key
    sorted_entries = sorted(stats.values(), key=lambda e: (e['testCategoryName'] or '', e['sortKey']))

    return [
        {
            'testCaseDescription': e['testCaseDescription'],
            'testCategoryName': e['testCategoryName'],
            'passed': e['passed'],
            'failed': e['failed'],
            'errored': e['errored'],
            'total': e['total'],
        }
        for e in sorted_entries
    ]
