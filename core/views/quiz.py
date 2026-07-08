# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils import timezone

from core.models import Quiz
from core.serializers.quiz import QuizSerializer, QuizQuestionSerializer
from core.serializers.generatedQuiz import GeneratedQuestionSetListSerializer
from core.serializers.studentQuiz import StaffQuizAttemptSerializer
from core.services.audit import record_audit_event
from core.views.template import ListProtectedViewSet
from core.permissions.helpers import isCourseAdmin, isCourseStaff
from core.permissions.permissions import (
    QuizPermissions, canGradeQuiz, canReviewGeneratedQuestions,
)


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

  @extend_schema(responses=GeneratedQuestionSetListSerializer(many=True))
  @action(detail=True, methods=['GET'])
  def generatedSets(self, request, pk=None):
    """Per-student generated question sets on this quiz, for review. Course admins
    always; other staff only when gradersCanReviewGenerated is on."""
    quiz = self.get_object()
    if not canReviewGeneratedQuestions(request.user, quiz):
      return Response({'detail': 'You do not have permission to review generated questions '
                                 'on this quiz.'}, status=status.HTTP_403_FORBIDDEN)
    sets = quiz.generatedSets.select_related('student', 'submission').prefetch_related(
        'questions').order_by('student__email')
    return Response(GeneratedQuestionSetListSerializer(
        sets, many=True, context={'request': request}).data)

  @extend_schema(
      request=None,
      responses=inline_serializer('PublishAllGeneratedResponse', {
          'approved': serializers.IntegerField(), 'skipped': serializers.IntegerField()}),
      description="Approve every generated set awaiting review on this quiz in one step "
                  "(course admins only). Sets with no questions are skipped.",
  )
  @action(detail=True, methods=['POST'])
  def publishAllGenerated(self, request, pk=None):
    quiz = self.get_object()
    if not (request.user.is_superuser or isCourseAdmin(request.user, quiz.course)):
      return Response({'detail': 'Only course admins can publish all generated sets.'},
                      status=status.HTTP_403_FORBIDDEN)
    approved = skipped = 0
    now = timezone.now()
    for gen_set in quiz.generatedSets.filter(status='ready').prefetch_related('questions'):
      if not gen_set.questions.exists():
        skipped += 1
        continue
      gen_set.status = 'approved'
      gen_set.approvedBy = request.user
      gen_set.approvedAt = now
      gen_set.save(update_fields=['status', 'approvedBy', 'approvedAt', 'modified'])
      approved += 1
    record_audit_event(course=quiz.course, event_type='quiz_generated_sets_published',
                       user=request.user, quiz=quiz, assignment=quiz.assignment,
                       meta={'title': quiz.title, 'approved': approved, 'skipped': skipped})
    return Response({'approved': approved, 'skipped': skipped}, status=status.HTTP_200_OK)

  @extend_schema(
      responses=inline_serializer('PromptVariable', {
          'token': serializers.CharField(), 'name': serializers.CharField(),
          'argument': serializers.CharField(allow_null=True), 'label': serializers.CharField(),
          'description': serializers.CharField(), 'kind': serializers.CharField()},
          many=True),
      description="The {variables} usable in this quiz's personalized-section prompts "
                  "(powers the prompt editor's autocomplete).",
  )
  @action(detail=True, methods=['GET'])
  def promptVariables(self, request, pk=None):
    quiz = self.get_object()
    if not (request.user.is_superuser or isCourseStaff(request.user, quiz.course)):
      return Response({'detail': 'Only course staff can list prompt variables.'},
                      status=status.HTTP_403_FORBIDDEN)
    from core.prompts.variables import VariableContext, describe_available_variables
    return Response(describe_available_variables(
        VariableContext(course=quiz.course, assignment=quiz.assignment)))
