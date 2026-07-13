# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Assignment Analytics Service

Provides aggregated analytics for assignment-level insights:
grade distribution, grader workload, grading timeline, test results summary,
rubric usage, score breakdown by category, grader consistency, submission attempts,
time-to-grade, late submissions, and feedback depth.
"""

import math
import statistics
from collections import Counter, defaultdict

from django.db.models import Avg, Count, F, Q, StdDev
from django.db.models.functions import TruncDay

from core.models import Assignment, Comment, RubricCategory, Submission, SubmissionTest


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


def get_rubric_usage(assignment: Assignment, limit: int = 15) -> list[dict]:
    """
    Count how many times each rubric comment was applied across all submissions.
    Returns the top N most-applied rubric comments with text, pointDelta, category, and count.
    """
    results = (
        Comment.objects.filter(
            file__submission__assignment=assignment,
            rubricComment__isnull=False,
        )
        .values(
            'rubricComment__id',
            'rubricComment__text',
            'rubricComment__pointDelta',
            'rubricComment__category__name',
        )
        .annotate(count=Count('id'))
        .order_by('-count')[:limit]
    )

    return [
        {
            'rubricCommentId': r['rubricComment__id'],
            'text': r['rubricComment__text'],
            'pointDelta': float(r['rubricComment__pointDelta']),
            'categoryName': r['rubricComment__category__name'],
            'count': r['count'],
        }
        for r in results
    ]


def get_score_by_category(assignment: Assignment) -> list[dict]:
    """
    Aggregate the total applied point deductions per rubric category per finalized submission.
    Returns mean/median/min/max deduction per category.
    """
    categories = RubricCategory.objects.filter(assignment=assignment)
    if not categories.exists():
        return []

    # Get all rubric-backed comments on finalized submissions, grouped by (submission, category)
    _comment_data = (
        Comment.objects.filter(
            file__submission__assignment=assignment,
            file__submission__isFinalized=True,
            rubricComment__isnull=False,
        )
        .values(
            'file__submission_id',
            'rubricComment__category__id',
            'rubricComment__category__name',
            'rubricComment__category__pointLimit',
        )
        .annotate(totalDelta=Count('id'))  # placeholder — we need sum of pointDelta
    )

    # Aggregate in Python to sum actual pointDeltas per (submission, category)
    raw = (
        Comment.objects.filter(
            file__submission__assignment=assignment,
            file__submission__isFinalized=True,
            rubricComment__isnull=False,
        )
        .select_related('rubricComment', 'rubricComment__category')
        .values_list(
            'file__submission_id',
            'rubricComment__category__id',
            'rubricComment__category__name',
            'rubricComment__category__pointLimit',
            'rubricComment__pointDelta',
        )
    )

    # Build: {category_id: {name, pointLimit, deductions: [sum_per_submission]}}
    cat_sub_totals: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    cat_info: dict[int, dict] = {}

    for sub_id, cat_id, cat_name, point_limit, point_delta in raw:
        cat_sub_totals[cat_id][sub_id] += float(point_delta)
        if cat_id not in cat_info:
            cat_info[cat_id] = {
                'categoryName': cat_name,
                'pointLimit': float(point_limit) if point_limit is not None else None,
            }

    result = []
    for cat_id, sub_totals in cat_sub_totals.items():
        deductions = list(sub_totals.values())
        if not deductions:
            continue
        info = cat_info[cat_id]
        result.append({
            'categoryName': info['categoryName'],
            'pointLimit': info['pointLimit'],
            'meanDeduction': round(statistics.mean(deductions), 2),
            'medianDeduction': round(statistics.median(deductions), 2),
            'minDeduction': round(min(deductions), 2),
            'maxDeduction': round(max(deductions), 2),
            'submissionCount': len(deductions),
        })

    result.sort(key=lambda x: x['categoryName'])
    return result


def get_grader_consistency(assignment: Assignment) -> list[dict]:
    """
    Compute mean grade and standard deviation per grader for finalized submissions.
    Helps identify graders who are significantly harsher or more lenient.
    """
    results = (
        Submission.objects.filter(
            assignment=assignment,
            isFinalized=True,
            grader__isnull=False,
        )
        .values(grader_email=F('grader__email'))
        .annotate(
            meanGrade=Avg('grade'),
            stddevGrade=StdDev('grade'),
            count=Count('id'),
        )
        .order_by('grader_email')
    )

    return [
        {
            'grader': r['grader_email'],
            'meanGrade': round(float(r['meanGrade']), 2) if r['meanGrade'] is not None else None,
            'stddevGrade': round(float(r['stddevGrade']), 2) if r['stddevGrade'] is not None else None,
            'count': r['count'],
        }
        for r in results
    ]


def get_submission_attempts(assignment: Assignment) -> dict:
    """
    Group submissions by student and analyze attempt patterns.
    Returns attempt distribution and average grade improvement.
    """
    submissions = (
        Submission.objects.filter(assignment=assignment)
        .prefetch_related('students')
        .order_by('dateUploaded')
        .values_list('id', 'grade', 'dateUploaded')
    )

    # Map submissions to their students
    sub_students: dict[int, list[str]] = defaultdict(list)
    for sub in Submission.objects.filter(assignment=assignment).prefetch_related('students'):
        for student in sub.students.all():
            sub_students[sub.id].append(student.email)

    # Group by student
    student_subs: dict[str, list[dict]] = defaultdict(list)
    for sub_id, grade, date_uploaded in submissions:
        for email in sub_students.get(sub_id, []):
            student_subs[email].append({
                'grade': float(grade) if grade is not None else None,
                'dateUploaded': date_uploaded,
            })

    # Sort each student's submissions by date
    for email in student_subs:
        student_subs[email].sort(key=lambda s: s['dateUploaded'] or '')

    # Compute attempt distribution
    attempt_counts: Counter[int] = Counter()
    grade_improvements: list[float] = []

    for _email, subs in student_subs.items():
        num_attempts = len(subs)
        attempt_counts[num_attempts] += 1

        # Grade improvement: last grade - first grade (if both exist)
        if num_attempts > 1:
            first_grade = subs[0]['grade']
            last_grade = subs[-1]['grade']
            if first_grade is not None and last_grade is not None:
                grade_improvements.append(last_grade - first_grade)

    attempt_distribution = [
        {'attempts': k, 'studentCount': v}
        for k, v in sorted(attempt_counts.items())
    ]

    return {
        'attemptDistribution': attempt_distribution,
        'avgGradeImprovement': round(statistics.mean(grade_improvements), 2) if grade_improvements else None,
        'studentsWithMultipleAttempts': sum(1 for c in attempt_counts if c > 1),
        'totalStudents': len(student_subs),
    }


def get_time_to_grade(assignment: Assignment) -> dict:
    """
    Compute turnaround time from upload to finalization (using `modified` as finalization proxy).
    Returns overall stats and per-grader breakdown.
    """
    finalized = Submission.objects.filter(
        assignment=assignment,
        isFinalized=True,
        dateUploaded__isnull=False,
    ).values_list('grader__email', 'dateUploaded', 'modified')

    if not finalized:
        return {'overall': None, 'byGrader': []}

    grader_turnarounds: dict[str, list[float]] = defaultdict(list)
    all_turnarounds: list[float] = []

    for grader_email, date_uploaded, modified in finalized:
        if date_uploaded and modified:
            delta = (modified - date_uploaded).total_seconds() / 3600.0  # hours
            if delta >= 0:
                all_turnarounds.append(delta)
                if grader_email:
                    grader_turnarounds[grader_email].append(delta)

    def _turnaround_stats(hours_list: list[float]) -> dict:
        if not hours_list:
            return {'meanHours': None, 'medianHours': None, 'minHours': None, 'maxHours': None}
        return {
            'meanHours': round(statistics.mean(hours_list), 1),
            'medianHours': round(statistics.median(hours_list), 1),
            'minHours': round(min(hours_list), 1),
            'maxHours': round(max(hours_list), 1),
        }

    by_grader = [
        {
            'grader': email,
            'count': len(hours),
            **_turnaround_stats(hours),
        }
        for email, hours in sorted(grader_turnarounds.items())
    ]

    return {
        'overall': _turnaround_stats(all_turnarounds),
        'byGrader': by_grader,
    }


def get_late_submission_stats(assignment: Assignment) -> dict | None:
    """
    Analyze submission timing relative to the assignment's uploadDueDate.
    Returns None if no due date is set.
    """
    if not assignment.uploadDueDate:
        return None

    due_date = assignment.uploadDueDate
    submissions = Submission.objects.filter(
        assignment=assignment,
        dateUploaded__isnull=False,
    ).values_list('dateUploaded', flat=True)

    on_time = 0
    late = 0
    late_by_day: Counter[int] = Counter()

    for date_uploaded in submissions:
        if date_uploaded <= due_date:
            on_time += 1
        else:
            late += 1
            days_late = max(1, (date_uploaded - due_date).days + 1)
            late_by_day[days_late] += 1

    late_by_day_list = [
        {'day': day, 'count': count}
        for day, count in sorted(late_by_day.items())
    ]

    return {
        'dueDate': due_date.isoformat(),
        'onTime': on_time,
        'late': late,
        'lateByDay': late_by_day_list,
    }


def get_feedback_depth(assignment: Assignment) -> dict:
    """
    Analyze comment volume per submission and per grader.
    Returns overall and per-grader feedback metrics.
    """
    # Per-submission comment counts
    sub_comments = (
        Comment.objects.filter(file__submission__assignment=assignment)
        .values('file__submission_id')
        .annotate(
            totalComments=Count('id'),
            rubricComments=Count('id', filter=Q(rubricComment__isnull=False)),
            freeformComments=Count('id', filter=Q(rubricComment__isnull=True)),
        )
    )

    if not sub_comments:
        return {'overall': None, 'byGrader': []}

    totals = [s['totalComments'] for s in sub_comments]
    overall = {
        'meanCommentsPerSubmission': round(statistics.mean(totals), 1),
        'medianCommentsPerSubmission': round(statistics.median(totals), 1),
        'totalSubmissionsWithComments': len(totals),
    }

    # Per-grader breakdown
    grader_data = (
        Comment.objects.filter(file__submission__assignment=assignment)
        .values(grader_email=F('file__submission__grader__email'))
        .annotate(
            totalComments=Count('id'),
            rubricComments=Count('id', filter=Q(rubricComment__isnull=False)),
            freeformComments=Count('id', filter=Q(rubricComment__isnull=True)),
            submissionsGraded=Count('file__submission_id', distinct=True),
        )
        .order_by('grader_email')
    )

    by_grader = [
        {
            'grader': g['grader_email'],
            'totalComments': g['totalComments'],
            'rubricComments': g['rubricComments'],
            'freeformComments': g['freeformComments'],
            'submissionsGraded': g['submissionsGraded'],
            'meanComments': round(g['totalComments'] / max(g['submissionsGraded'], 1), 1),
        }
        for g in grader_data
        if g['grader_email']
    ]

    return {
        'overall': overall,
        'byGrader': by_grader,
    }
