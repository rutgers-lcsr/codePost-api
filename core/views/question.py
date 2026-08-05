# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Assignment, Question, QuestionBank
from core.serializers.question import QuestionSerializer
from core.serializers.suggestedQuizQuestion import SuggestedQuizQuestionSerializer
from core.serializers.quizSuggestionJob import QuizSuggestionJobSerializer
from core.views.template import ListProtectedViewSet
from core.permissions.permissions import QuestionPermissions
from core.permissions.helpers import isCourseStaff, returnForbidden
from core.permissions.capabilities import Capability, require_capability


class QuestionViewSet(ListProtectedViewSet):
  """Quiz questions, each living in exactly one bank (with nested, writable choices)."""
  queryset = Question.objects.select_related('course', 'createdBy', 'bank').prefetch_related('choices').all()
  serializer_class = QuestionSerializer
  permission_classes = (IsAuthenticated, QuestionPermissions)

  def destroy(self, request, *args, **kwargs):
    # QuizResponses snapshot the question and SET_NULL, so deleting a used question no longer
    # raises ProtectedError; this stays as a clean-409 safety net for any future protected relation.
    try:
      return super().destroy(request, *args, **kwargs)
    except ProtectedError:
      return Response(
          {'error': 'in_use', 'message': 'This question has protected dependents and cannot be deleted.'},
          status=status.HTTP_409_CONFLICT,
      )

  def _resolve_target_bank(self, request):
    """Resolve the target bank from the request and check course-staff access."""
    try:
      bank_id = int(request.data.get('bankId'))
    except (TypeError, ValueError):
      return None, Response({'error': 'A valid bankId is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
    bank = get_object_or_404(QuestionBank, id=bank_id)
    if not (request.user.is_superuser or isCourseStaff(request.user, bank.course)):
      return None, returnForbidden()
    return bank, None

  @staticmethod
  def _parse_question_ids(request):
    """The questionIds list as ints, or None if any entry is malformed (→ 400, not 500)."""
    try:
      return [int(i) for i in (request.data.get('questionIds') or [])]
    except (TypeError, ValueError):
      return None

  @extend_schema(
      request=inline_serializer('BankQuestionsRequest', fields={
          'questionIds': serializers.ListField(child=serializers.IntegerField()),
          'bankId': serializers.IntegerField(),
      }),
      responses=QuestionSerializer(many=True),
      description="Move the given questions into another bank (re-points each question's bank).",
  )
  @action(detail=False, methods=['POST'])
  def moveToBank(self, request):
    bank, err = self._resolve_target_bank(request)
    if err:
      return err
    ids = self._parse_question_ids(request)
    if ids is None:
      return Response({'error': 'questionIds must be a list of integers.'},
                      status=status.HTTP_400_BAD_REQUEST)
    qs = Question.objects.filter(id__in=ids, course=bank.course)  # same-course safety
    moved_ids = list(qs.values_list('id', flat=True))
    qs.update(bank=bank, modified=timezone.now())  # queryset update bypasses BaseModel.save()
    questions = Question.objects.filter(id__in=moved_ids).prefetch_related('choices')
    return Response(QuestionSerializer(questions, many=True, context={'request': request}).data)

  @extend_schema(
      request=inline_serializer('BankCopyRequest', fields={
          'questionIds': serializers.ListField(child=serializers.IntegerField()),
          'bankId': serializers.IntegerField(),
      }),
      responses=QuestionSerializer(many=True),
      description="Copy the given questions (with their choices) into another bank as new questions.",
  )
  @action(detail=False, methods=['POST'])
  def copyToBank(self, request):
    bank, err = self._resolve_target_bank(request)
    if err:
      return err
    ids = self._parse_question_ids(request)
    if ids is None:
      return Response({'error': 'questionIds must be a list of integers.'},
                      status=status.HTTP_400_BAD_REQUEST)
    source = Question.objects.filter(id__in=ids, course=bank.course).prefetch_related('choices')
    new_questions = []
    with transaction.atomic():
      for q in source:
        copy = Question.objects.create(
            course=bank.course, bank=bank, questionType=q.questionType, text=q.text,
            description=q.description, points=q.points, generalFeedback=q.generalFeedback,
            partialCredit=q.partialCredit, numericTolerance=q.numericTolerance,
            language=q.language, starterCode=q.starterCode, referenceSolution=q.referenceSolution,
            source=q.source, createdBy=request.user, metadata=q.metadata,
        )
        for c in q.choices.all():
          copy.choices.create(text=c.text, isCorrect=c.isCorrect, sortKey=c.sortKey, feedback=c.feedback)
        new_questions.append(copy)
    return Response(QuestionSerializer(new_questions, many=True, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)

  @extend_schema(
      request=inline_serializer('RegenerateSuggestionRequest', fields={
          'assignment_id': serializers.IntegerField(required=False),
          'num_questions': serializers.IntegerField(required=False),
          'question_types': serializers.ListField(child=serializers.CharField(), required=False),
          'instructions': serializers.CharField(required=False),
      }),
      responses=QuizSuggestionJobSerializer,
      description="Generate a refreshed AI suggestion seeded from this existing question "
                  "(cross-semester update). The instructor reviews and accepts the suggestion. "
                  "Returns the generation job to poll via quizSuggestionJobs/{id}/ for status "
                  "and errors. Returns 403 when the course has the quiz_generation AI feature "
                  "turned off.",
  )
  @action(detail=True, methods=['POST'])
  def regenerateSuggestion(self, request, pk=None):
    """Enqueue an AI task to suggest an updated version of this question."""
    question = self.get_object()  # triggers object-level permission check
    require_capability(request.user, Capability.GENERATE_AI_QUIZ_QUESTIONS, question.course)
    from core.models import QuizSuggestionJob
    from core.tasks import generate_quiz_question_suggestions

    # A cross-course assignment_id would resolve the task's course to that other course and
    # inject the refresh suggestion there; require it to match the question's course.
    assignment_id = request.data.get('assignment_id')
    if assignment_id is not None:
      assignment = get_object_or_404(Assignment, id=assignment_id)
      if assignment.course_id != question.course_id:
        return Response({'error': 'Assignment must belong to the same course as the question.'},
                        status=status.HTTP_400_BAD_REQUEST)

    job = QuizSuggestionJob.objects.create(
        course=question.course, sourceQuestion=question,
        assignment_id=assignment_id, requestedBy=request.user)
    task = generate_quiz_question_suggestions.delay(
        requested_by_id=request.user.id,
        source_question_id=question.id,
        assignment_id=assignment_id,
        num_questions=request.data.get('num_questions', 1),
        question_types=request.data.get('question_types') or [question.questionType],
        instructions=request.data.get('instructions', '') or '',
        job_id=job.id,
    )
    # Queryset update (not job.save): under eager Celery the task may have already
    # advanced the DB row, and BaseModel.save would clobber it from a stale instance.
    QuizSuggestionJob.objects.filter(pk=job.pk).update(taskId=task.id)
    job.refresh_from_db()
    return Response(QuizSuggestionJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

  @extend_schema(responses=SuggestedQuizQuestionSerializer(many=True))
  @action(detail=True, methods=['GET'])
  def regenerationSuggestions(self, request, pk=None):
    """Pending AI refresh suggestions seeded from this question (for review/accept)."""
    question = self.get_object()
    suggestions = question.regeneration_suggestions.filter(status='pending')
    return Response(SuggestedQuizQuestionSerializer(suggestions, many=True, context={'request': request}).data)
