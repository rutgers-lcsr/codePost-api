# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""Student-facing quiz taking: start/resume an attempt, autosave answers, submit + auto-grade.

Kept separate from the staff-only QuizViewSet. Only the mixins students need are exposed
(create + retrieve + a few actions) — no list/update/destroy.
"""
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Course, Quiz, QuizAttempt
from core.permissions.helpers import isCourseMember, isStudent
from core.permissions.permissions import QuizAttemptPermissions
from core.serializers.studentQuiz import (
    StaffQuizAttemptSerializer,
    StudentQuizAttemptSerializer,
    StudentQuizResponseSerializer,
    StudentQuizSerializer,
)
from core.services import quiz_grading
from core.services.audit import record_audit_event


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

  def _attempt_context(self, attempt):
    return {
        'request': self.request,
        'reveal': quiz_grading.answers_visible(attempt.quiz, attempt),
        'revealScore': attempt.status == 'submitted',
    }

  def retrieve(self, request, *args, **kwargs):
    attempt = self.get_object()
    return Response(StudentQuizAttemptSerializer(attempt, context=self._attempt_context(attempt)).data)

  @extend_schema(
      request=inline_serializer('StartQuizAttemptRequest', {'quiz': serializers.IntegerField()}),
      responses=StudentQuizAttemptSerializer,
  )
  def create(self, request, *args, **kwargs):
    """Start a new attempt, or resume the student's in-progress one, for ``quiz``."""
    quiz_id = request.data.get('quiz')
    if not quiz_id:
      return Response({'detail': 'A quiz id is required.'}, status=status.HTTP_400_BAD_REQUEST)
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
    if not is_open:
      return Response({'detail': f'This quiz is not available ({reason}).'},
                      status=status.HTTP_403_FORBIDDEN)
    used = quiz.attempts.filter(student=user).count()
    if quiz.attemptsAllowed and used >= quiz.attemptsAllowed:
      return Response({'detail': 'No attempts remaining.'}, status=status.HTTP_403_FORBIDDEN)
    if not quiz_grading.quiz_has_content(quiz):
      return Response({'detail': 'This quiz has no questions yet.'}, status=status.HTTP_400_BAD_REQUEST)

    started = timezone.now()
    deadline = started + timedelta(minutes=quiz.timeLimitMinutes) if quiz.timeLimitMinutes else None
    if quiz.endAttemptsAtClose:
      close = quiz_grading.quiz_close_time(quiz, user, started)
      if close is not None:
        deadline = close if deadline is None else min(deadline, close)
    attempt = QuizAttempt.objects.create(
        quiz=quiz, student=user, attemptNumber=used + 1,
        startedAt=started, deadline=deadline, status='in_progress',
    )
    quiz_grading.build_attempt_responses(attempt)
    _record_attempt_event(attempt, 'quiz_attempt_started')
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
    if attempt.status != 'in_progress':
      return Response({'detail': 'This attempt is no longer open.'}, status=status.HTTP_400_BAD_REQUEST)
    if attempt.deadline and timezone.now() > attempt.deadline + SAVE_DEADLINE_GRACE:
      return Response({'detail': 'Time is up for this attempt.'}, status=status.HTTP_400_BAD_REQUEST)

    response = get_object_or_404(attempt.responses, pk=request.data.get('response'))
    if 'answerText' in request.data:
      response.answerText = request.data.get('answerText') or ''
      response.save()
    if 'selectedChoices' in request.data:
      valid = response.question.choices.filter(id__in=request.data.get('selectedChoices') or [])
      response.selectedChoices.set(valid)
    return Response(StudentQuizResponseSerializer(
        response, context={'request': request, 'reveal': False}).data)

  @extend_schema(request=None, responses=StudentQuizAttemptSerializer)
  @action(detail=True, methods=['POST'])
  def submit(self, request, pk=None):
    """Finalize and auto-grade the attempt."""
    attempt = self.get_object()
    if attempt.status != 'submitted':
      quiz_grading.grade_attempt(attempt)
      attempt.refresh_from_db()
      _record_attempt_event(attempt, 'quiz_attempt_submitted')
    return Response(StudentQuizAttemptSerializer(attempt, context=self._attempt_context(attempt)).data)

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
    if attempt.status != 'submitted':
      return Response({'detail': 'Only submitted attempts can be graded.'},
                      status=status.HTTP_400_BAD_REQUEST)
    response = get_object_or_404(attempt.responses, pk=request.data.get('response'))
    if response.question.questionType not in quiz_grading.MANUAL_TYPES:
      return Response({'detail': 'Only essay/code responses are graded manually.'},
                      status=status.HTTP_400_BAD_REQUEST)
    points = quiz_grading._parse_decimal(request.data.get('pointsEarned'))
    if points is None:
      return Response({'detail': 'pointsEarned must be a number.'}, status=status.HTTP_400_BAD_REQUEST)

    quiz_grading.apply_manual_grade(response, points, request.user,
                                    feedback=request.data.get('graderFeedback') or '')
    attempt.refresh_from_db()
    return Response(StaffQuizAttemptSerializer(
        attempt, context={'request': request, 'reveal': True, 'revealScore': True}).data)

  @extend_schema(
      parameters=[OpenApiParameter(name='quiz', type=int, location=OpenApiParameter.QUERY, required=True)],
      responses=StudentQuizAttemptSerializer(many=True),
  )
  @action(detail=False, methods=['GET'])
  def myAttempts(self, request):
    """The calling student's attempts for ``quiz``."""
    quiz = get_object_or_404(Quiz, pk=request.query_params.get('quiz'))
    attempts = quiz.attempts.filter(student=request.user).order_by('attemptNumber')
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
    course = get_object_or_404(Course, pk=request.query_params.get('course'))
    if not isCourseMember(request.user, course):
      return Response({'detail': 'Not a member of this course.'}, status=status.HTTP_403_FORBIDDEN)
    result = []
    for quiz in course.quizzes.filter(isPublished=True).select_related('assignment'):
      if not quiz_grading.quiz_has_content(quiz):
        continue  # skip quizzes with no fixed questions and no drawable bank questions
      is_open, _ = quiz_grading.quiz_availability(quiz, request.user)
      attempted = quiz.attempts.filter(student=request.user).exists()
      if quiz.assignment_id is not None:
        if quiz.assignment.isReleased or attempted:
          result.append(quiz)
      elif is_open or attempted:
        result.append(quiz)
    return Response(StudentQuizSerializer(result, many=True, context={'request': request}).data)
