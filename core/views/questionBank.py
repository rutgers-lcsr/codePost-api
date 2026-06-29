# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import QuestionBank, Quiz
from core.serializers.questionBank import QuestionBankSerializer
from core.serializers.question import QuestionSerializer
from core.views.template import ListProtectedViewSet
from core.permissions.permissions import QuestionBankPermissions


class QuestionBankViewSet(ListProtectedViewSet):
  """Course-level pools of quiz questions; each question belongs to exactly one bank."""
  queryset = QuestionBank.objects.select_related('course', 'createdBy').all()
  serializer_class = QuestionBankSerializer
  permission_classes = (IsAuthenticated, QuestionBankPermissions)

  @extend_schema(responses=QuestionSerializer(many=True))
  @action(detail=True, methods=['GET'])
  def questions(self, request, pk=None):
    """List the questions in this bank."""
    bank = self.get_object()
    questions = bank.questions.prefetch_related('choices').all()
    return Response(QuestionSerializer(questions, many=True, context={'request': request}).data)

  @extend_schema(parameters=[OpenApiParameter(
      name='force', type=bool, location=OpenApiParameter.QUERY,
      description='Delete even if the bank is used by a quiz (detaches its questions first).')])
  def destroy(self, request, *args, **kwargs):
    """Delete a bank. Blocked (409) if it's used by any quiz — either as a random-draw
    source or because one of its questions is in a quiz — unless ``force=true``. Deleting
    cascades: its questions (and their quiz memberships) and any random-draw groups go too."""
    bank = self.get_object()  # also enforces course-admin delete permission
    impacted = list(
        Quiz.objects.filter(Q(questionGroups__bank=bank) | Q(quizQuestions__question__bank=bank))
        .distinct()
        .values('id', 'title')
    )
    question_count = bank.questions.count()
    force = str(request.query_params.get('force', '')).lower() in ('1', 'true', 'yes')

    if impacted and not force:
      return Response(
          {
              'error': 'in_use',
              'message': f'This bank is used by {len(impacted)} quiz(zes).',
              'impactedQuizzes': impacted,
              'questionCount': question_count,
          },
          status=status.HTTP_409_CONFLICT,
      )

    bank.delete()
    return Response(
        {'deleted': True, 'impactedQuizzes': impacted, 'questionCount': question_count},
        status=status.HTTP_200_OK,
    )
