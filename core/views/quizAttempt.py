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
    StudentQuizAttemptSerializer,
    StudentQuizResponseSerializer,
    StudentQuizSerializer,
)
from core.services import quiz_grading


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
    if quiz.questionGroups.exists():
      return Response({'detail': 'This quiz uses random draws, which are not yet supported for taking.'},
                      status=status.HTTP_400_BAD_REQUEST)

    # Resume an existing in-progress attempt (auto-submitting it first if its time is up).
    existing = quiz.attempts.filter(student=user, status='in_progress').order_by('-attemptNumber').first()
    if existing is not None:
      if existing.deadline and timezone.now() > existing.deadline:
        quiz_grading.grade_attempt(existing)
      return Response(StudentQuizAttemptSerializer(existing, context=self._attempt_context(existing)).data)

    is_open, reason = quiz_grading.quiz_availability(quiz, user)
    if not is_open:
      return Response({'detail': f'This quiz is not available ({reason}).'},
                      status=status.HTTP_403_FORBIDDEN)
    used = quiz.attempts.filter(student=user).count()
    if quiz.attemptsAllowed and used >= quiz.attemptsAllowed:
      return Response({'detail': 'No attempts remaining.'}, status=status.HTTP_403_FORBIDDEN)
    if not quiz.quizQuestions.exists():
      return Response({'detail': 'This quiz has no questions yet.'}, status=status.HTTP_400_BAD_REQUEST)

    started = timezone.now()
    deadline = started + timedelta(minutes=quiz.timeLimitMinutes) if quiz.timeLimitMinutes else None
    attempt = QuizAttempt.objects.create(
        quiz=quiz, student=user, attemptNumber=used + 1,
        startedAt=started, deadline=deadline, status='in_progress',
    )
    quiz_grading.build_attempt_responses(attempt)
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
    if attempt.deadline and timezone.now() > attempt.deadline:
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
    return Response(StudentQuizAttemptSerializer(attempt, context=self._attempt_context(attempt)).data)

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
    """Published quizzes in ``course`` the caller can take now (or has already attempted)."""
    course = get_object_or_404(Course, pk=request.query_params.get('course'))
    if not isCourseMember(request.user, course):
      return Response({'detail': 'Not a member of this course.'}, status=status.HTTP_403_FORBIDDEN)
    result = []
    for quiz in course.quizzes.filter(isPublished=True):
      if quiz.questionGroups.exists() or not quiz.quizQuestions.exists():
        continue  # random-draw quizzes aren't takeable yet; skip empty quizzes
      is_open, _ = quiz_grading.quiz_availability(quiz, request.user)
      if is_open or quiz.attempts.filter(student=request.user).exists():
        result.append(quiz)
    return Response(StudentQuizSerializer(result, many=True, context={'request': request}).data)
