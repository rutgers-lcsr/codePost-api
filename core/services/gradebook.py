# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Course gradebook: one grid of every active student × every assignment and quiz.

Semantics:
- Rows: the active roster (course.students) ordered by email; students with nothing graded
  still get a row. Inactive students are excluded.
- Assignment columns: every assignment (model ordering). A cell shows the student's best
  submission — finalized preferred, then newest upload, then highest id (mirrors
  quiz_grading.LATEST_SUBMISSION_ORDERING) — and its grade only once finalized; an
  unfinalized submission renders as pending.
- Quiz columns: quizzes that are published or already have submitted attempts. A cell is
  the official score per the quiz's scoringPolicy (quiz_grading.official_score), null until
  a fully graded attempt exists. maxScore is the student's own (random-draw/generated
  sections vary per student).
- Totals count graded cells only: earned/possible accumulate finalized assignment grades
  and official quiz scores — pending or missing work never counts against the student.
  percent is null until something is graded.

Both the gradebook endpoint (JSON grid) and the CSV export are built from this one
function so they can never drift apart.
"""
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from core.models import QuizAttempt, Submission
from core.services import quiz_grading

# Sorts below datetimes of real uploads so a submission without dateUploaded loses ties.
_EPOCH = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)


def build_gradebook(course, assignment_ids=None, quiz_ids=None, section=None):
  """The gradebook for ``course``: column metadata plus one row per active student.

  ``assignment_ids`` / ``quiz_ids`` restrict the columns (None means all; an empty set
  means none) and ``section`` restricts the rows to students in that section — totals
  are computed over the included columns only, so a filtered export stays self-consistent.

  Runs a constant number of queries regardless of course size (students, assignments,
  one course-wide submissions query, one course-wide attempts query, quizzes).
  """
  students = list(course.students.all().order_by('email'))
  assignments = list(course.assignments.all())
  if assignment_ids is not None:
    assignments = [a for a in assignments if a.id in assignment_ids]

  # Section name(s) per student email (a student can belong to several sections).
  sections_by_email = {}
  for name, email in course.sections.values_list('name', 'students__email'):
    if email is not None:
      sections_by_email.setdefault(email, []).append(name)
  if section:
    students = [s for s in students if section in sections_by_email.get(s.email, [])]

  # Best submission per (student email, assignment): finalized first, then newest.
  # The values_list joins the students M2M, so partner submissions yield one row each.
  best = {}
  sub_rows = Submission.objects.filter(assignment__course=course).values_list(
      'students__email', 'assignment_id', 'grade', 'isFinalized', 'dateUploaded', 'id')
  for email, assignment_id, grade, is_finalized, date_uploaded, sub_id in sub_rows:
    if email is None:
      continue
    key = (email, assignment_id)
    pref = (bool(is_finalized), date_uploaded or _EPOCH, sub_id)
    if key not in best or pref > best[key][0]:
      best[key] = (pref, grade, bool(is_finalized))

  # Every submitted attempt in the course, grouped per (quiz, student) — the whole-course
  # generalization of the batching in QuizViewSet.results (no per-student queries).
  attempts_by = {}
  for attempt in QuizAttempt.objects.filter(quiz__course=course, status='submitted') \
      .select_related('student').order_by('attemptNumber'):
    attempts_by.setdefault((attempt.quiz_id, attempt.student_id), []).append(attempt)
  quiz_ids_with_attempts = {quiz_id for quiz_id, _ in attempts_by}
  quizzes = [q for q in course.quizzes.order_by('title', 'id')
             if q.isPublished or q.id in quiz_ids_with_attempts]
  if quiz_ids is not None:
    quizzes = [q for q in quizzes if q.id in quiz_ids]

  rows = []
  for student in students:
    earned = Decimal('0')
    possible = Decimal('0')
    assignment_cells = []
    for assignment in assignments:
      found = best.get((student.email, assignment.id))
      is_finalized = found is not None and bool(found[2])
      # Re-check `found` (rather than relying on is_finalized implying it) so the
      # indexing below is provably safe to the type checker.
      grade = found[1] if (found is not None and is_finalized) else None
      if grade is not None:
        earned += grade
        possible += assignment.points or Decimal('0')
      assignment_cells.append({
          'assignment': assignment.id,
          'grade': grade,
          'hasSubmission': found is not None,
          'isFinalized': is_finalized,
      })
    quiz_cells = []
    for quiz in quizzes:
      attempts = attempts_by.get((quiz.id, student.id), [])
      official = quiz_grading.official_score(quiz, student, attempts=attempts) if attempts else None
      if official is not None:
        earned += official[0]
        possible += official[1] or Decimal('0')
      quiz_cells.append({
          'quiz': quiz.id,
          'score': official[0] if official else None,
          'maxScore': official[1] if official else None,
          'needsGrading': any(a.needsManualGrading for a in attempts),
          'hasAttempts': bool(attempts),
      })
    percent = (earned / possible * Decimal('100')).quantize(Decimal('0.01')) if possible > 0 else None
    rows.append({
        'student': student.email,
        'section': ', '.join(sorted(sections_by_email.get(student.email, []))) or None,
        'assignmentCells': assignment_cells,
        'quizCells': quiz_cells,
        'totalEarned': earned,
        'totalPossible': possible,
        'percent': percent,
    })

  return {
      'assignments': [{'id': a.id, 'name': a.name, 'points': a.points} for a in assignments],
      'quizzes': [{'id': q.id, 'title': q.title} for q in quizzes],
      'rows': rows,
  }
