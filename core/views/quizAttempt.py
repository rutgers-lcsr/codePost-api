# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Student-facing quiz taking: start/resume an attempt, autosave answers, submit + auto-grade.

Kept separate from the staff-only QuizViewSet. Only the mixins students need are exposed
(create + retrieve + a few actions) — no list/update/destroy.
"""
import secrets
from collections import defaultdict
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Course, Quiz, QuizAttempt, QuizResponse
from core.permissions.helpers import isCourseMember, isStudent
from core.permissions.permissions import QuizAttemptPermissions, canGradeQuiz
from core.serializers.studentQuiz import (
    StaffQuizAttemptSerializer,
    StudentQuizAttemptSerializer,
    StudentQuizResponseSerializer,
    StudentQuizSerializer,
    staff_reveal_context,
)
from core.services import quiz_grading
from core.services.audit import record_audit_event


def _require_int(value):
  """Coerce a client-supplied id to int, or None if it isn't a valid integer.

  Guards against get_object_or_404(pk='abc') raising ValueError → 500 (it only catches
  DoesNotExist). Callers return 400 on None.
  """
  try:
    return int(value)
  except (TypeError, ValueError):
    return None


def _record_grading_event(attempt, response, event_type, grader):
  """Log a manual-grading event (graded/reopened) to the course activity log.

  Attributed to the grader; the affected student rides along in meta."""
  quiz = attempt.quiz
  meta = {
      'quizTitle': quiz.title,
      'student': attempt.student.email,
      'attemptNumber': attempt.attemptNumber,
      'questionType': (response.questionSnapshot or {}).get('type'),
      'pointsEarned': str(response.pointsEarned) if response.pointsEarned is not None else None,
  }
  record_audit_event(course=quiz.course, event_type=event_type, user=grader,
                     quiz=quiz, assignment=quiz.assignment, meta=meta)


def _record_attempt_event(attempt, event_type):
  """Log a quiz-attempt event to the course activity log."""
  quiz = attempt.quiz
  meta = {'quizTitle': quiz.title, 'attemptNumber': attempt.attemptNumber}
  if attempt.status == 'submitted':
    meta['score'] = str(attempt.score) if attempt.score is not None else None
    meta['maxScore'] = str(attempt.maxScore) if attempt.maxScore is not None else None
  record_audit_event(course=quiz.course, event_type=event_type, user=attempt.student,
                     quiz=quiz, assignment=quiz.assignment, meta=meta)

# Small grace so the auto-submit's final answer flush (fired right at the deadline) still lands
# despite network latency. Interactive editing already stops at the deadline (the UI disables
# inputs on auto-submit), so this only covers in-flight saves — not extra working time.
SAVE_DEADLINE_GRACE = timedelta(seconds=5)


class QuizAttemptViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
  """A student's quiz attempts. Students operate only on their own; staff may read."""
  queryset = QuizAttempt.objects.select_related('quiz', 'quiz__assignment', 'student').all()
  serializer_class = StudentQuizAttemptSerializer
  permission_classes = (IsAuthenticated, QuizAttemptPermissions)

  def get_queryset(self):
    # Only the read-only retrieve prefetches responses' question/generatedQuestion (they feed
    # referenceSolution in the staff view). The mutating actions must NOT prefetch: they grade
    # a response then recompute totals off attempt.responses, which would read a stale cache.
    qs = super().get_queryset()
    if getattr(self, 'action', None) == 'retrieve':
      qs = qs.prefetch_related(
          Prefetch('responses', queryset=QuizResponse.objects.select_related('question', 'generatedQuestion')))
    return qs

  def _attempt_context(self, attempt):
    return {
        'request': self.request,
        'reveal': quiz_grading.answers_visible(attempt.quiz, attempt),
        'revealScore': quiz_grading.scores_visible(attempt.quiz, attempt),
        # Scores-only quizzes stop sending question content once the attempt is submitted.
        'revealResponses': attempt.status != 'submitted' or attempt.quiz.showResponses,
    }

  @extend_schema(responses=StaffQuizAttemptSerializer)
  def retrieve(self, request, *args, **kwargs):
    attempt = self.get_object()
    # Quiz graders / admins reading someone else's attempt get the grading projection
    # (student identity, answers, scores, and the answer key revealed); the owner keeps the
    # policy-gated student view. Assignment-only graders are NOT quiz graders — the answer
    # key must not leak to them (mirrors the attempts/results list gate).
    if request.user != attempt.student and canGradeQuiz(request.user, attempt.quiz.course):
      return Response(StaffQuizAttemptSerializer(
          attempt, context=staff_reveal_context(request)).data)
    # The owner is a student here: when the quiz disallows reviewing past submissions, a
    # submitted attempt can no longer be reopened (an in-progress attempt is still theirs).
    if attempt.status == 'submitted' and not attempt.quiz.allowSubmissionReview:
      return Response({'detail': 'Reviewing past submissions is disabled for this quiz.'},
                      status=status.HTTP_403_FORBIDDEN)
    return Response(StudentQuizAttemptSerializer(attempt, context=self._attempt_context(attempt)).data)

  @extend_schema(
      request=inline_serializer('StartQuizAttemptRequest', {
          'quiz': serializers.IntegerField(),
          'accessCode': serializers.CharField(required=False, allow_blank=True),
      }),
      responses=StudentQuizAttemptSerializer,
  )
  def create(self, request, *args, **kwargs):
    """Start a new attempt, or resume the student's in-progress one, for ``quiz``.

    A late student whose quiz has closed may pass ``accessCode`` to start anyway: a match on
    the quiz's access code bypasses the close (only), and the attempt keeps its full time limit.
    """
    quiz_id = _require_int(request.data.get('quiz'))
    if quiz_id is None:
      return Response({'detail': 'A valid quiz id is required.'}, status=status.HTTP_400_BAD_REQUEST)
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    user = request.user

    if not isStudent(user, quiz.course):
      return Response({'detail': 'Only enrolled students can take this quiz.'},
                      status=status.HTTP_403_FORBIDDEN)

    # Resume an existing in-progress attempt (auto-submitting it first if its time is up).
    existing = quiz.attempts.filter(student=user, status='in_progress').order_by('-attemptNumber').first()
    if existing is not None:
      if existing.deadline and timezone.now() > existing.deadline:
        quiz_grading.grade_attempt(existing)
        _record_attempt_event(existing, 'quiz_attempt_autosubmitted')
      return Response(StudentQuizAttemptSerializer(existing, context=self._attempt_context(existing)).data)

    is_open, reason = quiz_grading.quiz_availability(quiz, user)
    bypass = False
    if not is_open:
      # A late student may start a closed quiz with the quiz's access code — but only when the
      # quiz has actually closed (not, say, 'not_yet_open' or 'no_submission_yet'), and only if a
      # code is set. Nothing else about availability is bypassed.
      if reason in quiz_grading.LATE_BYPASSABLE_REASONS and quiz.accessCode:
        submitted = (request.data.get('accessCode') or '').strip()
        if submitted and secrets.compare_digest(submitted, quiz.accessCode):
          bypass = True
        else:
          return Response({'detail': 'This quiz has closed — enter the access code to continue.',
                           'reason': reason, 'accessCodeRequired': True},
                          status=status.HTTP_403_FORBIDDEN)
      else:
        return Response({'detail': f'This quiz is not available ({reason}).'},
                        status=status.HTTP_403_FORBIDDEN)
    used = quiz.attempts.filter(student=user).count()
    if quiz.attemptsAllowed and used >= quiz.attemptsAllowed:
      return Response({'detail': 'No attempts remaining.'}, status=status.HTTP_403_FORBIDDEN)
    if not quiz_grading.quiz_has_content(quiz):
      return Response({'detail': 'This quiz has no questions yet.'}, status=status.HTTP_400_BAD_REQUEST)

    started = timezone.now()
    deadline = quiz_grading.compute_attempt_deadline(quiz, user, started, bypass_close=bypass)
    try:
      with transaction.atomic():
        attempt = QuizAttempt.objects.create(
            quiz=quiz, student=user, attemptNumber=used + 1,
            startedAt=started, deadline=deadline, status='in_progress',
            closeBypassed=bypass,
        )
        quiz_grading.build_attempt_responses(attempt)
    except IntegrityError:
      # A concurrent start (double-click) won the (quiz, student, attemptNumber) unique race.
      # Return the in-progress attempt it created rather than a 500.
      existing = quiz.attempts.filter(student=user, status='in_progress').order_by('-attemptNumber').first()
      if existing is not None:
        return Response(StudentQuizAttemptSerializer(existing, context=self._attempt_context(existing)).data)
      raise
    _record_attempt_event(attempt, 'quiz_attempt_started_late' if bypass else 'quiz_attempt_started')
    return Response(StudentQuizAttemptSerializer(attempt, context=self._attempt_context(attempt)).data,
                    status=status.HTTP_201_CREATED)

  @extend_schema(
      request=inline_serializer('SaveQuizAnswerRequest', {
          'response': serializers.IntegerField(),
          'answerText': serializers.CharField(required=False, allow_blank=True),
          'selectedChoices': serializers.ListField(child=serializers.IntegerField(), required=False),
      }),
      responses=StudentQuizResponseSerializer,
  )
  @action(detail=True, methods=['PATCH'])
  def saveAnswer(self, request, pk=None):
    """Autosave a single response within an in-progress, not-yet-expired attempt."""
    attempt = self.get_object()  # ownership enforced by has_object_permission (PATCH ⇒ owner)
    if attempt.quiz.course.archived:
      return Response({'detail': 'This course is archived.'}, status=status.HTTP_403_FORBIDDEN)
    if attempt.status != 'in_progress':
      return Response({'detail': 'This attempt is no longer open.'}, status=status.HTTP_400_BAD_REQUEST)
    if attempt.deadline and timezone.now() > attempt.deadline + SAVE_DEADLINE_GRACE:
      return Response({'detail': 'Time is up for this attempt.'}, status=status.HTTP_400_BAD_REQUEST)

    response = get_object_or_404(attempt.responses, pk=request.data.get('response'))

    # Enforce no-backtracking server-side (otherwise the setting is only advisory in the UI):
    # once the student has moved past a question, its answer can't be changed via a direct call.
    # Only sequential mode locks earlier questions — with all questions on one page students
    # answer in any order, and allowBacktracking may still be False left over from a previous
    # sequential configuration (the builder hides the toggle outside sequential mode).
    if attempt.quiz.oneQuestionAtATime and not attempt.quiz.allowBacktracking \
        and response.sortKey < attempt.furthestIndex:
      return Response({'detail': 'Returning to earlier questions is not allowed.'},
                      status=status.HTTP_400_BAD_REQUEST)

    if 'answerText' in request.data:
      response.answerText = request.data.get('answerText') or ''
      response.save()
    if 'selectedChoices' in request.data:
      valid_ids = {c['id'] for c in (response.questionSnapshot or {}).get('choices', [])}
      requested = request.data.get('selectedChoices') or []
      response.selectedChoiceKeys = [i for i in requested if i in valid_ids]
      response.save()

    if response.sortKey > attempt.furthestIndex:
      attempt.furthestIndex = response.sortKey
      attempt.save()
    return Response(StudentQuizResponseSerializer(
        response, context={'request': request, 'reveal': False}).data)

  @extend_schema(request=None, responses=StudentQuizAttemptSerializer)
  @action(detail=True, methods=['POST'])
  def submit(self, request, pk=None):
    """Finalize and auto-grade the attempt."""
    attempt = self.get_object()
    if attempt.quiz.course.archived:
      return Response({'detail': 'This course is archived.'}, status=status.HTTP_403_FORBIDDEN)
    if attempt.status != 'submitted':
      quiz_grading.grade_attempt(attempt)
      attempt.refresh_from_db()
      _record_attempt_event(attempt, 'quiz_attempt_submitted')
    return Response(StudentQuizAttemptSerializer(attempt, context=self._attempt_context(attempt)).data)

  def _manual_grading_guard(self, attempt, response):
    """Shared preconditions for grading/reopening a response, or None when allowed."""
    if attempt.quiz.course.archived:
      return Response({'detail': 'This course is archived.'}, status=status.HTTP_403_FORBIDDEN)
    if attempt.status != 'submitted':
      return Response({'detail': 'Only submitted attempts can be graded.'},
                      status=status.HTTP_400_BAD_REQUEST)
    if (response.questionSnapshot or {}).get('type') not in quiz_grading.MANUAL_TYPES:
      return Response({'detail': 'Only essay/code responses are graded manually.'},
                      status=status.HTTP_400_BAD_REQUEST)
    return None

  @extend_schema(
      request=inline_serializer('GradeQuizResponseRequest', {
          'response': serializers.IntegerField(),
          'pointsEarned': serializers.DecimalField(max_digits=6, decimal_places=2),
          'graderFeedback': serializers.CharField(required=False, allow_blank=True),
      }),
      responses=StaffQuizAttemptSerializer,
  )
  @action(detail=True, methods=['POST'])
  def gradeResponse(self, request, pk=None):
    """Manually grade one essay/code response (quiz graders and course admins only —
    gated by QuizAttemptPermissions). Recomputes the attempt's score and pass state."""
    attempt = self.get_object()
    response = get_object_or_404(attempt.responses, pk=request.data.get('response'))
    denied = self._manual_grading_guard(attempt, response)
    if denied:
      return denied
    points = quiz_grading._parse_decimal(request.data.get('pointsEarned'))
    if points is None:
      return Response({'detail': 'pointsEarned must be a number.'}, status=status.HTTP_400_BAD_REQUEST)

    quiz_grading.apply_manual_grade(response, points, request.user,
                                    feedback=request.data.get('graderFeedback') or '')
    attempt.refresh_from_db()
    response.refresh_from_db()
    _record_grading_event(attempt, response, 'quiz_response_graded', request.user)
    return Response(StaffQuizAttemptSerializer(
        attempt, context=staff_reveal_context(request)).data)

  @extend_schema(
      request=inline_serializer('ReopenQuizResponseRequest', {
          'response': serializers.IntegerField(),
      }),
      responses=StaffQuizAttemptSerializer,
  )
  @action(detail=True, methods=['POST'])
  def reopenResponse(self, request, pk=None):
    """Send a manually graded essay/code response back to the grading queue (undo the
    grade). The feedback text is kept as a draft; the attempt's totals are refreshed."""
    attempt = self.get_object()
    response = get_object_or_404(attempt.responses, pk=request.data.get('response'))
    denied = self._manual_grading_guard(attempt, response)
    if denied:
      return denied
    if response.needsManualGrading:
      return Response({'detail': 'This response has not been graded yet.'},
                      status=status.HTTP_400_BAD_REQUEST)

    quiz_grading.reopen_manual_grade(response)
    attempt.refresh_from_db()
    response.refresh_from_db()
    _record_grading_event(attempt, response, 'quiz_response_grade_reopened', request.user)
    return Response(StaffQuizAttemptSerializer(
        attempt, context=staff_reveal_context(request)).data)

  @extend_schema(
      request=inline_serializer('RunQuizResponseCodeRequest', {
          'response': serializers.IntegerField(),
      }),
      responses=StaffQuizAttemptSerializer,
      description="Run a student's code answer in the sandbox (quiz graders and course admins "
                  "only). Dispatches an async execution; poll the attempt to see the result "
                  "land in the response's codeExecution field.",
  )
  @action(detail=True, methods=['POST'])
  def runCode(self, request, pk=None):
    """Sandbox-execute one code response's answer so a grader can see what it produces.
    Async: sets codeExecution.status='running' and dispatches RunQuizResponseCode; the
    grading UI polls the attempt until it lands."""
    attempt = self.get_object()
    if attempt.quiz.course.archived:
      return Response({'detail': 'This course is archived.'}, status=status.HTTP_403_FORBIDDEN)
    response = get_object_or_404(attempt.responses, pk=request.data.get('response'))
    if attempt.status != 'submitted':
      return Response({'detail': 'Only submitted attempts can be run.'},
                      status=status.HTTP_400_BAD_REQUEST)
    if (response.questionSnapshot or {}).get('type') != 'code':
      return Response({'detail': 'Only code responses can be executed.'},
                      status=status.HTTP_400_BAD_REQUEST)
    if not (response.answerText or '').strip():
      return Response({'detail': 'This response has no code to run.'},
                      status=status.HTTP_400_BAD_REQUEST)
    # Guard against a double-click re-dispatching while a run is in flight (but let a
    # stale 'running' — a task that died without writing back — be retried after a while).
    existing = response.codeExecution or {}
    if existing.get('status') == 'running':
      requested_at = existing.get('requestedAt')
      if requested_at and (timezone.now() - timezone.datetime.fromisoformat(requested_at)).total_seconds() < 180:
        return Response({'detail': 'This answer is already running.'},
                        status=status.HTTP_409_CONFLICT)

    response.codeExecution = {
        'status': 'running',
        'requestedBy': request.user.email,
        'requestedAt': timezone.now().isoformat(),
    }
    response.save(update_fields=['codeExecution', 'modified'])

    from autograder.run import RunQuizResponseCode
    RunQuizResponseCode.delay(response.id)
    return Response(StaffQuizAttemptSerializer(
        attempt, context=staff_reveal_context(request)).data)

  @extend_schema(
      request=inline_serializer('SetOfficialAttemptRequest', {
          'official': serializers.BooleanField(required=False, default=True),
      }),
      responses=StaffQuizAttemptSerializer,
      description="Pin this submitted attempt as the student's official score, overriding the "
                  "quiz's scoringPolicy — or unpin with official=false to return to the policy. "
                  "Quiz graders and course admins only; at most one pin per student.",
  )
  @action(detail=True, methods=['POST'])
  def setOfficial(self, request, pk=None):
    attempt = self.get_object()
    if attempt.quiz.course.archived:
      return Response({'detail': 'This course is archived.'}, status=status.HTTP_403_FORBIDDEN)
    if attempt.status != 'submitted':
      return Response({'detail': 'Only submitted attempts can be pinned as official.'},
                      status=status.HTTP_400_BAD_REQUEST)
    official = bool(request.data.get('official', True))
    with transaction.atomic():
      # At most one pin per (quiz, student) — pinning moves it, unpinning restores the policy.
      attempt.quiz.attempts.filter(student=attempt.student).exclude(pk=attempt.pk).update(
          isOfficialOverride=False, modified=timezone.now())
      attempt.isOfficialOverride = official
      attempt.save()
    record_audit_event(
        course=attempt.quiz.course,
        event_type='quiz_attempt_pinned_official' if official else 'quiz_attempt_unpinned_official',
        user=request.user, quiz=attempt.quiz, assignment=attempt.quiz.assignment,
        meta={'student': attempt.student.email, 'attemptNumber': attempt.attemptNumber})
    return Response(StaffQuizAttemptSerializer(attempt, context=staff_reveal_context(request)).data)

  @extend_schema(
      parameters=[OpenApiParameter(name='quiz', type=int, location=OpenApiParameter.QUERY, required=True)],
      responses=StudentQuizAttemptSerializer(many=True),
  )
  @action(detail=False, methods=['GET'])
  def myAttempts(self, request):
    """The calling student's attempts for ``quiz``."""
    quiz_id = _require_int(request.query_params.get('quiz'))
    if quiz_id is None:
      return Response({'detail': 'A valid quiz id is required.'}, status=status.HTTP_400_BAD_REQUEST)
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    attempts = quiz.attempts.filter(student=request.user).order_by('attemptNumber')
    # Review disabled: submitted attempts can't be reopened, so the review history is empty.
    if not quiz.allowSubmissionReview:
      attempts = attempts.exclude(status='submitted')
    data = [StudentQuizAttemptSerializer(a, context=self._attempt_context(a)).data for a in attempts]
    return Response(data)

  @extend_schema(
      parameters=[OpenApiParameter(name='course', type=int, location=OpenApiParameter.QUERY, required=True)],
      responses=StudentQuizSerializer(many=True),
  )
  @action(detail=False, methods=['GET'])
  def availableQuizzes(self, request):
    """Published quizzes in ``course`` the caller should see.

    Attached quizzes surface once their assignment is released — even while the quiz
    itself is still locked — so the assignment card can show them with a reason.
    Standalone quizzes surface only when open now or already attempted.
    """
    course_id = _require_int(request.query_params.get('course'))
    if course_id is None:
      return Response({'detail': 'A valid course id is required.'}, status=status.HTTP_400_BAD_REQUEST)
    course = get_object_or_404(Course, pk=course_id)
    if not isCourseMember(request.user, course):
      return Response({'detail': 'Not a member of this course.'}, status=status.HTTP_403_FORBIDDEN)
    quizzes = list(course.quizzes.filter(isPublished=True).select_related('assignment'))
    # One query for the caller's attempts across these quizzes, grouped by quiz — so neither
    # the inclusion check here nor the serializer's per-card counts/score fire a query per quiz.
    attempts_by_quiz = defaultdict(list)
    for a in QuizAttempt.objects.filter(quiz__in=quizzes, student=request.user):
      attempts_by_quiz[a.quiz_id].append(a)
    availability = {}
    result = []
    for quiz in quizzes:
      if not quiz_grading.quiz_has_content(quiz):
        continue  # skip quizzes with no fixed questions and no drawable bank questions
      is_open, reason = quiz_grading.quiz_availability(quiz, request.user)
      availability[quiz.id] = (is_open, reason)  # computed once, reused by the serializer
      attempted = bool(attempts_by_quiz.get(quiz.id))
      # A closed standalone quiz with a late-access code still surfaces, so a late student can
      # see the card and enter the code (attached quizzes already surface once released).
      code_unlockable = bool(quiz.accessCode) and reason in quiz_grading.LATE_BYPASSABLE_REASONS
      if quiz.assignment_id is not None:
        if quiz.assignment.isReleased or attempted:
          result.append(quiz)
      elif is_open or attempted or code_unlockable:
        result.append(quiz)
    return Response(StudentQuizSerializer(result, many=True, context={
        'request': request,
        'availability': availability,
        'studentAttempts': attempts_by_quiz,
    }).data)
