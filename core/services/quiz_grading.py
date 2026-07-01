# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""Quiz taking: attempt materialization, auto-grading, availability, and answer-reveal logic.

Phase 2 slice 1 — auto-gradable question types only. Essay/code responses are flagged
for manual grading (a later slice) and excluded from the auto-graded score.
"""
import random
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from core.models import QuizResponse

AUTO_GRADED_TYPES = {'multiple_choice', 'multiple_answers', 'true_false', 'short_answer', 'numerical'}
MANUAL_TYPES = {'essay', 'code'}


# --------------------------------------------------------------------------- #
# Attempt materialization
# --------------------------------------------------------------------------- #

def build_attempt_responses(attempt):
  """Snapshot the quiz's fixed questions as QuizResponse rows for this attempt.

  Order follows the quiz's QuizQuestion order, randomized when shuffleQuestions is set.
  Random-draw question groups are not materialized here (deferred slice).
  """
  quiz = attempt.quiz
  memberships = list(quiz.quizQuestions.select_related('question').all())
  positions = list(range(len(memberships)))
  if quiz.shuffleQuestions:
    random.shuffle(positions)
  for position, idx in enumerate(positions):
    m = memberships[idx]
    pts = m.pointsOverride if m.pointsOverride is not None else m.question.points
    QuizResponse.objects.create(attempt=attempt, question=m.question, sortKey=position, points=pts)


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #

def _normalize_text(s):
  return (s or '').strip().casefold()


def _parse_decimal(s):
  try:
    return Decimal(str(s).strip())
  except (InvalidOperation, AttributeError, ValueError):
    return None


def grade_response(response):
  """Auto-grade one response in place (caller saves). Manual types are flagged, not scored."""
  question = response.question
  qtype = question.questionType

  if qtype in MANUAL_TYPES:
    response.needsManualGrading = True
    response.isCorrect = None
    response.pointsEarned = None
    return

  correct_choices = list(question.choices.filter(isCorrect=True))
  is_correct = False

  if qtype in ('multiple_choice', 'true_false', 'multiple_answers'):
    selected_ids = {c.id for c in response.selectedChoices.all()}
    correct_ids = {c.id for c in correct_choices}
    is_correct = bool(correct_ids) and selected_ids == correct_ids
  elif qtype == 'short_answer':
    accepted = {_normalize_text(c.text) for c in correct_choices}
    is_correct = bool(accepted) and _normalize_text(response.answerText) in accepted
  elif qtype == 'numerical':
    student_val = _parse_decimal(response.answerText)
    accepted = [_parse_decimal(c.text) for c in correct_choices]
    is_correct = student_val is not None and any(a is not None and a == student_val for a in accepted)

  response.needsManualGrading = False
  response.isCorrect = is_correct
  response.pointsEarned = response.points if is_correct else Decimal('0')


def grade_attempt(attempt):
  """Grade all responses, set the attempt's score/maxScore/needsManualGrading/passed, submit it."""
  total_max = Decimal('0')
  total_earned = Decimal('0')
  needs_manual = False
  for response in attempt.responses.all():
    grade_response(response)
    response.save()
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
  attempt.save()


def _compute_passed(attempt):
  """Pass/fail against quiz.passingScore (percent or points). None when no threshold."""
  quiz = attempt.quiz
  threshold = quiz.passingScore
  if threshold is None:
    return None
  score = attempt.score or Decimal('0')
  if quiz.passingScoreUnit == 'points':
    return score >= threshold
  # percent
  if not attempt.maxScore or attempt.maxScore <= 0:
    return None
  return (score / attempt.maxScore) * Decimal('100') >= threshold


def official_score(quiz, student):
  """The student's official (score, maxScore) per quiz.scoringPolicy, or None if no graded attempt."""
  attempts = [a for a in quiz.attempts.filter(student=student, status='submitted') if a.score is not None]
  if not attempts:
    return None
  policy = quiz.scoringPolicy
  if policy == 'latest':
    chosen = max(attempts, key=lambda a: a.attemptNumber)
    return (chosen.score, chosen.maxScore)
  if policy == 'average':
    avg = sum((a.score for a in attempts), Decimal('0')) / len(attempts)
    latest = max(attempts, key=lambda a: a.attemptNumber)
    return (avg, latest.maxScore)
  # highest (default) — by score ratio
  chosen = max(attempts, key=lambda a: (a.score / a.maxScore) if a.maxScore else Decimal('0'))
  return (chosen.score, chosen.maxScore)


# --------------------------------------------------------------------------- #
# Availability + answer reveal
# --------------------------------------------------------------------------- #

def quiz_is_closed(quiz, now=None):
  """Whether the quiz's taking window has closed (standalone: availableUntil; attached: uploadDueDate)."""
  now = now or timezone.now()
  if quiz.assignment_id is None:
    return bool(quiz.availableUntil and now > quiz.availableUntil)
  due = quiz.assignment.uploadDueDate
  return bool(due and now > due)


def quiz_availability(quiz, student, now=None):
  """Return (is_open: bool, reason: str) for this student. reason is a short machine code."""
  now = now or timezone.now()
  if not quiz.isPublished:
    return (False, 'not_published')

  if quiz.assignment_id is None:
    if quiz.availableFrom and now < quiz.availableFrom:
      return (False, 'not_yet_open')
    if quiz.availableUntil and now > quiz.availableUntil:
      return (False, 'closed')
    return (True, 'open')

  assignment = quiz.assignment
  if not assignment.isReleased:
    return (False, 'assignment_not_released')
  trigger = quiz.assignmentTrigger
  if trigger == 'during':
    if assignment.uploadDueDate and now > assignment.uploadDueDate:
      return (False, 'assignment_closed')
    return (True, 'open')
  if trigger == 'after_assignment':
    if assignment.uploadDueDate and now > assignment.uploadDueDate:
      return (True, 'open')
    return (False, 'assignment_still_open')
  if trigger == 'after_submission':
    has_sub = student is not None and student.student_submissions.filter(assignment=assignment).exists()
    return (True, 'open') if has_sub else (False, 'no_submission_yet')
  if trigger == 'after_feedback':
    return (True, 'open') if assignment.feedbackReleased else (False, 'feedback_not_released')
  return (False, 'unavailable')


def answers_visible(quiz, attempt, now=None):
  """Whether correct answers / per-choice feedback may be revealed for this attempt."""
  policy = quiz.showCorrectAnswers
  if policy == 'never':
    return False
  if policy == 'after_submit':
    return attempt is not None and attempt.status == 'submitted'
  if policy == 'after_close':
    return quiz_is_closed(quiz, now)
  return False
