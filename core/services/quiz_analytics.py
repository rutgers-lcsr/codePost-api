# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Course-level quiz grading analytics: per-quiz manual-grading totals and per-grader
counts, powering the instructor's quiz grading-progress page."""
from django.db.models import Count, F, Max, Q

from core.models import QuizResponse


def get_quiz_grading_progress(course) -> dict:
    """Manual-grading progress across the course's published quizzes (submitted attempts
    only).

    graded = manually graded (gradedBy set); pending = awaiting manual grading
    (needsManualGrading). The two states are disjoint, so graded + pending == totalManual.
    Every published quiz appears (zeros when it has no manual responses) so the UI's column
    set is stable. Graders who left the course keep their rows — this is accountability
    data, not a roster.
    """
    manual = QuizResponse.objects.filter(
        attempt__quiz__course=course,
        attempt__quiz__isPublished=True,
        attempt__status='submitted',
    ).filter(Q(needsManualGrading=True) | Q(gradedBy__isnull=False))

    per_quiz = {
        row['quizId']: row
        for row in manual.values(quizId=F('attempt__quiz_id')).annotate(
            totalManual=Count('id'),
            graded=Count('id', filter=Q(gradedBy__isnull=False)),
            pending=Count('id', filter=Q(needsManualGrading=True)))
    }
    quizzes = [
        {'id': quiz.id, 'title': quiz.title,
         'totalManual': per_quiz.get(quiz.id, {}).get('totalManual', 0),
         'graded': per_quiz.get(quiz.id, {}).get('graded', 0),
         'pending': per_quiz.get(quiz.id, {}).get('pending', 0)}
        for quiz in course.quizzes.filter(isPublished=True).order_by('id')
    ]

    grader_rows: dict[str, dict] = {}
    for row in (manual.filter(gradedBy__isnull=False)
                .values(graderEmail=F('gradedBy__email'), quizId=F('attempt__quiz_id'))
                .annotate(graded=Count('id'), lastGradedAt=Max('gradedAt'))
                .order_by()):  # clear default ordering so the GROUP BY stays 2-column
        entry = grader_rows.setdefault(row['graderEmail'], {
            'grader': row['graderEmail'], 'totalGraded': 0, 'lastGradedAt': None,
            'perQuiz': {}})
        entry['totalGraded'] += row['graded']
        entry['perQuiz'][row['quizId']] = row['graded']
        if row['lastGradedAt'] and (entry['lastGradedAt'] is None
                                    or row['lastGradedAt'] > entry['lastGradedAt']):
            entry['lastGradedAt'] = row['lastGradedAt']

    graders = sorted(grader_rows.values(), key=lambda r: (-r['totalGraded'], r['grader']))
    return {'quizzes': quizzes, 'graders': graders,
            'pendingUngraded': sum(q['pending'] for q in quizzes)}
