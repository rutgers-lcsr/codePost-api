# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Quiz
from core.serializers.quiz import QuizSerializer, QuizQuestionSerializer
from core.serializers.studentQuiz import StaffQuizAttemptSerializer
from core.services.audit import record_audit_event
from core.views.template import ListProtectedViewSet
from core.permissions.helpers import isCourseAdmin
from core.permissions.permissions import QuizPermissions, canGradeQuiz


class QuizViewSet(ListProtectedViewSet):
  """Quizzes: authoring containers of questions, optionally attached to an assignment.

  Attach a quiz to an existing assignment by PATCHing its ``assignment`` field.
  """
  queryset = Quiz.objects.select_related('course', 'assignment', 'createdBy').prefetch_related(
      'quizQuestions__question').all()
  serializer_class = QuizSerializer
  permission_classes = (IsAuthenticated, QuizPermissions)

  def perform_create(self, serializer):
    quiz = serializer.save()
    record_audit_event(course=quiz.course, event_type='quiz_created', user=self.request.user,
                       quiz=quiz, assignment=quiz.assignment,
                       meta={'title': quiz.title, 'isPublished': quiz.isPublished})

  def perform_update(self, serializer):
    was_published = serializer.instance.isPublished
    quiz = serializer.save()
    if quiz.isPublished != was_published:
      event_type = 'quiz_published' if quiz.isPublished else 'quiz_unpublished'
    else:
      event_type = 'quiz_updated'
    record_audit_event(course=quiz.course, event_type=event_type, user=self.request.user,
                       quiz=quiz, assignment=quiz.assignment, meta={'title': quiz.title})

  def perform_destroy(self, instance):
    course, assignment, title, quiz_id = (
        instance.course, instance.assignment, instance.title, instance.id)
    instance.delete()
    record_audit_event(course=course, event_type='quiz_deleted', user=self.request.user,
                       assignment=assignment, meta={'title': title, 'quizId': quiz_id})

  @extend_schema(responses=QuizQuestionSerializer(many=True))
  @action(detail=True, methods=['GET'])
  def questions(self, request, pk=None):
    """List this quiz's question memberships, in order."""
    quiz = self.get_object()
    memberships = quiz.quizQuestions.select_related('question').all()
    return Response(QuizQuestionSerializer(memberships, many=True, context={'request': request}).data)

  @extend_schema(
      parameters=[OpenApiParameter(name='needsGrading', type=bool, location=OpenApiParameter.QUERY,
                                   required=False, description='Only attempts awaiting manual grading.')],
      responses=StaffQuizAttemptSerializer(many=True),
  )
  @action(detail=True, methods=['GET'])
  def attempts(self, request, pk=None):
    """Submitted attempts on this quiz, for grading — quiz graders and course admins only."""
    quiz = self.get_object()
    if not canGradeQuiz(request.user, quiz.course):
      return Response({'detail': 'Only quiz graders and course admins can view attempts for grading.'},
                      status=status.HTTP_403_FORBIDDEN)
    attempts = quiz.attempts.filter(status='submitted').select_related(
        'student', 'quiz').prefetch_related('responses').order_by('student__email', 'attemptNumber')
    if request.query_params.get('needsGrading') in ('true', 'True', '1'):
      attempts = attempts.filter(needsManualGrading=True)
    return Response(StaffQuizAttemptSerializer(
        attempts, many=True, context={'request': request, 'reveal': True, 'revealScore': True}).data)

  @extend_schema(
      request=None,
      responses=inline_serializer('ResetQuizAttemptsResponse', {'deleted': serializers.IntegerField()}),
      description="Delete ALL student attempts for this quiz (course admins only). Use after a "
                  "substantive edit so students retake from scratch. Irreversible; responses cascade.",
  )
  @action(detail=True, methods=['POST'])
  def resetAttempts(self, request, pk=None):
    quiz = self.get_object()
    if not (request.user.is_superuser or isCourseAdmin(request.user, quiz.course)):
      return Response({'detail': 'Only course admins can reset attempts.'},
                      status=status.HTTP_403_FORBIDDEN)
    deleted, _ = quiz.attempts.all().delete()
    record_audit_event(course=quiz.course, event_type='quiz_attempts_reset', user=request.user,
                       quiz=quiz, assignment=quiz.assignment, meta={'title': quiz.title})
    return Response({'deleted': deleted}, status=status.HTTP_200_OK)
