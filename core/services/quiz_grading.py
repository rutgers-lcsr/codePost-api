# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""Quiz taking: attempt materialization, grading, availability, and answer-reveal logic.

MC/multi-answer/true-false/short-answer/numerical responses auto-grade on submit.
Essay/code responses are flagged for manual grading (apply_manual_grade /
reopen_manual_grade, driven by the quizAttempts gradeResponse/reopenResponse actions)
and excluded from the score until graded.
"""
import random
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from core.models import QuizResponse

AUTO_GRADED_TYPES = {'multiple_choice', 'multiple_answers', 'true_false', 'short_answer', 'numerical'}
MANUAL_TYPES = {'essay', 'code'}


# --------------------------------------------------------------------------- #
# Attempt materialization
# --------------------------------------------------------------------------- #

def _question_snapshot(question):
  """An immutable copy of a question (and its choices) stored on each QuizResponse so the
  attempt is unaffected by later edits/deletion of the live question."""
  return {
      'questionId': question.id,
      'type': question.questionType,
      'text': question.text,
      'description': question.description,
      'starterCode': question.starterCode,
      'language': question.language,
      'generalFeedback': question.generalFeedback,
      'choices': [
          {'id': c.id, 'text': c.text, 'isCorrect': c.isCorrect,
           'feedback': c.feedback, 'sortKey': c.sortKey}
          for c in question.choices.all()
      ],
  }


def _generated_question_snapshot(gq):
  """An immutable copy of a per-student GeneratedQuizQuestion — the same shape as
  ``_question_snapshot`` (zero provenance) with ``questionId: None`` (there is no live
  Question row) and synthetic 1-based choice ids from ``choicesData``."""
  return {
      'questionId': None,
      'type': gq.questionType,
      'text': gq.text,
      'description': gq.description,
      'starterCode': gq.starterCode,
      'language': gq.language,
      'generalFeedback': '',
      'choices': [
          {'id': i + 1, 'text': c.get('text', ''), 'isCorrect': bool(c.get('isCorrect')),
           'feedback': c.get('feedback', ''), 'sortKey': i}
          for i, c in enumerate(gq.choicesData or [])
      ],
  }


def build_attempt_responses(attempt):
  """Snapshot the quiz's questions as QuizResponse rows for this attempt.

  Fixed questions come first (in QuizQuestion order); each random-draw group then picks
  ``pickCount`` random questions from its bank (worth ``pointsPerQuestion``); the student's
  approved per-student generated questions come last (with ``question=None`` — grading runs
  off the snapshot). A question already used in the attempt is skipped so it never appears
  twice (the (attempt, question) pair is unique). The whole set is shuffled when
  ``shuffleQuestions`` is set. Each response stores a full ``questionSnapshot`` so the
  attempt survives later question edits/deletion.
  """
  quiz = attempt.quiz
  picked = []  # list of (question_or_none, points, snapshot)
  used_ids = set()

  def add(question, points):
    if question.id in used_ids:
      return
    used_ids.add(question.id)
    picked.append((question, points, _question_snapshot(question)))

  for m in quiz.quizQuestions.select_related('question').prefetch_related('question__choices').all():
    add(m.question, m.pointsOverride if m.pointsOverride is not None else m.question.points)

  for group in quiz.questionGroups.select_related('bank').prefetch_related('bank__questions__choices').all():
    pool = [q for q in group.bank.questions.all() if q.id not in used_ids]
    for question in random.sample(pool, min(group.pickCount, len(pool))):
      add(question, group.pointsPerQuestion)

  gen_set = quiz.generatedSets.filter(student=attempt.student, status='approved').first()
  if gen_set is not None:
    for gq in gen_set.questions.all():
      picked.append((None, gq.points, _generated_question_snapshot(gq)))

  if quiz.shuffleQuestions:
    random.shuffle(picked)
  responses = [
      QuizResponse(attempt=attempt, question=question, sortKey=position, points=points,
                   questionSnapshot=snapshot)
      for position, (question, points, snapshot) in enumerate(picked)
  ]
  QuizResponse.objects.bulk_create(responses)


def quiz_has_content(quiz):
  """Whether the quiz has any takeable questions — fixed, drawable from a group's bank,
  or generated per student (availability separately gates on the student's approved set)."""
  if quiz.quizQuestions.exists():
    return True
  if quiz.generatedSections.exists():
    return True
  return any(g.bank.questions.exists() for g in quiz.questionGroups.select_related('bank').all())


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #

def _normalize_text(s):
  return (s or '').strip().casefold()


def _parse_decimal(s):
  try:
    d = Decimal(str(s).strip())
  except (InvalidOperation, AttributeError, ValueError):
    return None
  # Reject NaN / sNaN / Infinity: Decimal() accepts them, but comparing a signaling NaN
  # raises InvalidOperation, and they're never valid numeric answers/points anyway.
  if not d.is_finite():
    return None
  return d


def grade_response(response):
  """Auto-grade one response in place from its questionSnapshot (caller saves). Manual types
  are flagged, not scored."""
  snap = response.questionSnapshot or {}
  qtype = snap.get('type')

  if qtype in MANUAL_TYPES:
    response.needsManualGrading = True
    response.isCorrect = None
    response.pointsEarned = None
    return

  correct_choices = [c for c in snap.get('choices', []) if c.get('isCorrect')]
  is_correct = False

  if qtype in ('multiple_choice', 'true_false', 'multiple_answers'):
    selected_ids = set(response.selectedChoiceKeys or [])
    correct_ids = {c['id'] for c in correct_choices}
    is_correct = bool(correct_ids) and selected_ids == correct_ids
  elif qtype == 'short_answer':
    accepted = {_normalize_text(c['text']) for c in correct_choices}
    is_correct = bool(accepted) and _normalize_text(response.answerText) in accepted
  elif qtype == 'numerical':
    student_val = _parse_decimal(response.answerText)
    accepted = [_parse_decimal(c['text']) for c in correct_choices]
    is_correct = student_val is not None and any(a is not None and a == student_val for a in accepted)

  response.needsManualGrading = False
  response.isCorrect = is_correct
  response.pointsEarned = response.points if is_correct else Decimal('0')


def grade_attempt(attempt):
  """Grade all responses, set the attempt's score/maxScore/needsManualGrading/passed, submit it.

  Wrapped in a single transaction so a mid-grade failure can't leave some responses graded
  while the attempt stays in_progress; responses are written in one bulk_update.
  """
  total_max = Decimal('0')
  total_earned = Decimal('0')
  needs_manual = False
  responses = list(attempt.responses.all())
  graded_at = timezone.now()
  for response in responses:
    grade_response(response)
    response.modified = graded_at  # bulk_update bypasses BaseModel.save()
    total_max += response.points or Decimal('0')
    if response.needsManualGrading:
      needs_manual = True
    elif response.pointsEarned is not None:
      total_earned += response.pointsEarned

  attempt.score = total_earned
  attempt.maxScore = total_max
  attempt.needsManualGrading = needs_manual
  attempt.passed = None if needs_manual else _compute_passed(attempt)
  attempt.status = 'submitted'
  attempt.submittedAt = timezone.now()
  with transaction.atomic():
    if responses:
      QuizResponse.objects.bulk_update(
          responses, ['needsManualGrading', 'isCorrect', 'pointsEarned', 'modified'])
    attempt.save()


def apply_manual_grade(response, points_earned, grader, feedback=''):
  """Record a manual grade on one (essay/code) response and refresh the attempt's totals.

  Clamps points to [0, response.points]. Unlike grade_attempt, this never re-runs
  auto-grading, so existing scores are preserved.
  """
  points = max(Decimal('0'), min(_parse_decimal(points_earned) or Decimal('0'), response.points))
  response.pointsEarned = points
  response.isCorrect = None  # manual grades aren't binary
  response.needsManualGrading = False
  response.graderFeedback = feedback or ''
  response.gradedBy = grader
  response.save()
  recompute_attempt_totals(response.attempt)


def reopen_manual_grade(response):
  """Send a manually graded (essay/code) response back to the grading queue.

  Keeps graderFeedback as a draft for the next grader; refreshes the attempt's totals
  (score drops the reopened points and needsManualGrading/passed reset accordingly)."""
  response.pointsEarned = None
  response.isCorrect = None
  response.needsManualGrading = True
  response.gradedBy = None
  response.save()
  recompute_attempt_totals(response.attempt)


def recompute_attempt_totals(attempt):
  """Re-derive score / needsManualGrading / passed from the stored responses (no regrading)."""
  responses = list(attempt.responses.all())
  attempt.score = sum((r.pointsEarned for r in responses if r.pointsEarned is not None), Decimal('0'))
  attempt.maxScore = sum((r.points or Decimal('0') for r in responses), Decimal('0'))
  attempt.needsManualGrading = any(r.needsManualGrading for r in responses)
  attempt.passed = None if attempt.needsManualGrading else _compute_passed(attempt)
  attempt.save()


def _compute_passed(attempt):
  """Pass/fail against quiz.passingScore (percent or points). None when no threshold."""
  return _passed_for(attempt.quiz, attempt.score or Decimal('0'), attempt.maxScore)


def _passed_for(quiz, score, max_score):
  """Pass/fail for a raw (score, maxScore) against quiz.passingScore. None when no threshold."""
  threshold = quiz.passingScore
  if threshold is None:
    return None
  if quiz.passingScoreUnit == 'points':
    return score >= threshold
  # percent
  if not max_score or max_score <= 0:
    return None
  return (score / max_score) * Decimal('100') >= threshold


def _attempt_metric(quiz, attempt):
  """Ranking value for the 'highest' policy: absolute points when scoring by pooled points or
  a points threshold, otherwise the score ratio (percentage)."""
  if quiz.multiAttemptScoreMethod == 'pooled' or quiz.passingScoreUnit == 'points':
    return attempt.score or Decimal('0')
  return (attempt.score / attempt.maxScore) if attempt.maxScore else Decimal('0')


def official_score(quiz, student):
  """The student's official (score, maxScore) per quiz.scoringPolicy and multiAttemptScoreMethod,
  or None if no fully graded attempt. Attempts still awaiting manual grading are excluded — their
  stored score is only the auto-graded portion.

  'highest'/'latest' return a real attempt's (score, maxScore), so the denominator always
  matches. 'average' combines attempts per the method — 'pooled' pools points (Σearned/Σpossible),
  'by_unit' averages by the passing unit (percentage, or points) — never pairing one attempt's
  score with another's max.
  """
  attempts = [a for a in quiz.attempts.filter(student=student, status='submitted')
              if a.score is not None and not a.needsManualGrading]
  if not attempts:
    return None
  policy = quiz.scoringPolicy
  if policy == 'latest':
    chosen = max(attempts, key=lambda a: a.attemptNumber)
    return (chosen.score, chosen.maxScore)
  if policy == 'highest':
    chosen = max(attempts, key=lambda a: _attempt_metric(quiz, a))
    return (chosen.score, chosen.maxScore)
  # average
  n = len(attempts)
  mean_score = sum((a.score for a in attempts), Decimal('0')) / n
  mean_max = sum((a.maxScore or Decimal('0') for a in attempts), Decimal('0')) / n
  if quiz.multiAttemptScoreMethod == 'pooled' or quiz.passingScoreUnit == 'points':
    # Pooled points (mean_score/mean_max == Σearned/Σpossible), or the average of raw points
    # for a points threshold. Both are represented directly by (mean_score, mean_max).
    return (mean_score, mean_max)
  # by_unit percentage: the mean of per-attempt ratios, rendered against the mean max so the
  # displayed fraction and the pass check both reflect the average percentage.
  mean_ratio = sum(((a.score / a.maxScore) if a.maxScore else Decimal('0') for a in attempts),
                   Decimal('0')) / n
  return (mean_ratio * mean_max, mean_max)


def official_passed(quiz, student, official=None):
  """Pass/fail for the student's official score. None when no threshold or no graded attempt.
  Pass ``official`` to reuse an already-computed official_score result."""
  if official is None:
    official = official_score(quiz, student)
  if official is None:
    return None
  return _passed_for(quiz, official[0], official[1])


# --------------------------------------------------------------------------- #
# Availability + answer reveal
# --------------------------------------------------------------------------- #

def _earliest_submission_time(student, assignment):
  if student is None:
    return None
  sub = student.student_submissions.filter(assignment=assignment).order_by('dateUploaded').first()
  return sub.dateUploaded if sub is not None else None


def _student_feedback_visible(student, assignment):
  """Whether this student can actually see feedback on their OWN submission — i.e. they
  submitted and feedback is visible to them: the assignment released feedback, or it's in
  live-feedback mode and their submission is finalized (the self-paced case)."""
  if student is None:
    return False
  subs = student.student_submissions.filter(assignment=assignment)
  if not subs.exists():
    return False
  if assignment.feedbackReleased:
    return True
  if assignment.liveFeedbackMode:
    return subs.filter(isFinalized=True).exists()
  return False


def _generated_questions_ready(quiz, student):
  """Whether this student may take a quiz with generated sections: True when the quiz has
  none, or when the student's set is approved. Staff previews (student=None) never pass —
  there is nothing student-specific to materialize."""
  if not quiz.generatedSections.exists():
    return True
  if student is None:
    return False
  return quiz.generatedSets.filter(student=student, status='approved').exists()


def quiz_close_time(quiz, student, now=None):
  """When the quiz stops being available, or None if it has no explicit close.

  Attached quizzes use ``closeEvent`` (+ ``closeOffsetMinutes``); standalone quizzes use
  ``availableUntil``. The ``submission`` event is per-student.
  """
  if quiz.assignment_id is None:
    return quiz.availableUntil

  offset = timedelta(minutes=quiz.closeOffsetMinutes or 0)
  event = quiz.closeEvent
  if event == 'assignment_due':
    due = quiz.assignment.uploadDueDate
    return due + offset if due else None
  if event == 'submission':
    submitted = _earliest_submission_time(student, quiz.assignment)
    return submitted + offset if submitted else None
  if event == 'feedback_released':
    released = quiz.assignment.feedbackReleasedAt
    return released + offset if released else None
  if event == 'fixed_date':
    return quiz.availableUntil
  return None


def quiz_is_closed(quiz, student=None, now=None):
  """Whether the quiz's taking window has closed for this student."""
  now = now or timezone.now()
  close = quiz_close_time(quiz, student, now)
  return bool(close and now >= close)


def quiz_availability(quiz, student, now=None):
  """Return (is_open: bool, reason: str) for this student. reason is a short machine code."""
  now = now or timezone.now()
  if quiz.course.archived:
    return (False, 'course_archived')
  if not quiz.isPublished:
    return (False, 'not_published')

  if quiz.assignment_id is None:
    if quiz.availableFrom and now < quiz.availableFrom:
      return (False, 'not_yet_open')
    if quiz.availableUntil and now > quiz.availableUntil:
      return (False, 'closed')
    # Defense in depth: sections require an attached assignment, but a quiz could have
    # been detached historically — never open without the student's approved set.
    if not _generated_questions_ready(quiz, student):
      return (False, 'questions_not_ready')
    return (True, 'open')

  assignment = quiz.assignment
  if not assignment.isReleased:
    return (False, 'assignment_not_released')
  trigger = quiz.assignmentTrigger
  if trigger == 'during':
    if assignment.uploadDueDate and now > assignment.uploadDueDate:
      return (False, 'assignment_closed')
  elif trigger == 'after_assignment':
    if not (assignment.uploadDueDate and now > assignment.uploadDueDate):
      return (False, 'assignment_still_open')
  elif trigger == 'after_submission':
    if not (student is not None and student.student_submissions.filter(assignment=assignment).exists()):
      return (False, 'no_submission_yet')
  elif trigger == 'after_feedback':
    if not assignment.feedbackReleased:
      return (False, 'feedback_not_released')
  elif trigger == 'after_student_feedback':
    if not _student_feedback_visible(student, assignment):
      return (False, 'student_feedback_not_ready')
  else:
    return (False, 'unavailable')

  # Per-student generated questions must be approved before the quiz opens for that
  # student (after the trigger checks, so more actionable reasons like
  # 'no_submission_yet' surface first).
  if not _generated_questions_ready(quiz, student):
    return (False, 'questions_not_ready')

  # Open per the trigger — now apply the explicit close.
  close = quiz_close_time(quiz, student, now)
  if close and now >= close:
    return (False, 'closed')
  return (True, 'open')


def answers_visible(quiz, attempt, now=None):
  """Whether correct answers / per-choice feedback may be revealed for this attempt."""
  policy = quiz.showCorrectAnswers
  if policy == 'never':
    return False
  # Answers only ever reveal on a SUBMITTED attempt — never while it is still in progress,
  # or a student could read the key mid-attempt (e.g. after the quiz closes) and then answer.
  if attempt is None or attempt.status != 'submitted':
    return False
  if policy == 'after_submit':
    return True
  if policy == 'after_close':
    return quiz_is_closed(quiz, attempt.student, now)
  return False
