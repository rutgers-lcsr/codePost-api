# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Question, QuestionBank, SuggestedQuizQuestion
from core.serializers.suggestedQuizQuestion import SuggestedQuizQuestionSerializer
from core.serializers.question import QuestionSerializer
from core.views.template import ListProtectedViewSet
from core.permissions.permissions import SuggestedQuizQuestionPermissions

from logging import getLogger
logger = getLogger(__name__)


def _create_choices(question, choices_data):
  """Create QuestionChoice rows from a suggestion's choicesData list."""
  for i, c in enumerate(choices_data or []):
    if not isinstance(c, dict):
      continue
    question.choices.create(
        text=c.get('text', ''),
        isCorrect=bool(c.get('isCorrect', c.get('is_correct', False))),
        sortKey=c.get('sortKey', i),
        feedback=c.get('feedback', '') or '',
    )


class SuggestedQuizQuestionViewSet(ListProtectedViewSet):
  """AI-suggested quiz questions for instructors. Staff-only.

  A pending suggestion can be edited (PATCH) and then accepted into a real, editable
  Question (authored by the instructor) or rejected.
  """
  queryset = SuggestedQuizQuestion.objects.select_related(
      'assignment', 'assignment__course', 'sourceQuestion', 'sourceQuestion__course',
      'acceptedBy', 'acceptedQuestion',
  ).all()
  serializer_class = SuggestedQuizQuestionSerializer
  permission_classes = (IsAuthenticated, SuggestedQuizQuestionPermissions)

  @extend_schema(
      request=inline_serializer('AcceptSuggestionRequest', fields={
          'bankId': serializers.IntegerField(required=False),
      }),
      responses=QuestionSerializer,
      description="Accept this suggestion. A fresh suggestion creates a new Question in the "
                  "given bank (bankId required); a refresh (sourceQuestion set) updates that "
                  "existing question in place. The resulting question is authored by the instructor.",
  )
  @action(detail=True, methods=['POST'])
  def accept(self, request, pk=None):
    suggestion = self.get_object()
    user = request.user

    if suggestion.status != 'pending':
      return Response({'error': f'Suggestion is already {suggestion.status}.'},
                      status=status.HTTP_400_BAD_REQUEST)

    if suggestion.sourceQuestion_id is not None:
      # Refresh: update the existing question in place — preserve identity, author,
      # bank/quiz memberships. The instructor remains the author.
      question = suggestion.sourceQuestion
      question.questionType = suggestion.questionType
      question.text = suggestion.text
      question.points = suggestion.points
      question.language = suggestion.language
      question.starterCode = suggestion.starterCode
      question.referenceSolution = suggestion.referenceSolution
      question.save()
      question.choices.all().delete()
      _create_choices(question, suggestion.choicesData)
    else:
      # Fresh: create a new question (in a bank) authored by the accepting instructor.
      bank_id = request.data.get('bankId')
      if not bank_id:
        return Response({'error': 'bankId is required to accept a new question into a bank.'},
                        status=status.HTTP_400_BAD_REQUEST)
      bank = get_object_or_404(QuestionBank, id=bank_id)
      # The permission class validated the caller as staff of the suggestion's course; require
      # the target bank to be in that same course so a suggestion can't be accepted into (and
      # inject a Question into) a course the caller has no role in.
      if bank.course_id != suggestion.course.id:
        return Response({'error': 'Bank must belong to the same course as the suggestion.'},
                        status=status.HTTP_403_FORBIDDEN)
      question = Question.objects.create(
          course=bank.course,
          bank=bank,
          questionType=suggestion.questionType,
          text=suggestion.text,
          points=suggestion.points,
          language=suggestion.language,
          starterCode=suggestion.starterCode,
          referenceSolution=suggestion.referenceSolution,
          source='ai',
          createdBy=user,
          metadata={'generatedFromSuggestion': True, **(suggestion.generationMetadata or {})},
      )
      _create_choices(question, suggestion.choicesData)

    suggestion.status = 'accepted'
    suggestion.acceptedBy = user
    suggestion.acceptedQuestion = question
    suggestion.save()

    logger.info(f"Quiz suggestion {suggestion.id} accepted by {user.email}, question {question.id}")
    return Response(QuestionSerializer(question, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)

  @extend_schema(request=None, responses=SuggestedQuizQuestionSerializer, description="Reject this suggestion.")
  @action(detail=True, methods=['POST'])
  def reject(self, request, pk=None):
    suggestion = self.get_object()
    if suggestion.status != 'pending':
      return Response({'error': f'Suggestion is already {suggestion.status}.'},
                      status=status.HTTP_400_BAD_REQUEST)
    suggestion.status = 'rejected'
    suggestion.save()
    return Response(SuggestedQuizQuestionSerializer(suggestion).data)
