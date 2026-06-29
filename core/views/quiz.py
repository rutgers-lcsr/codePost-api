# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Quiz
from core.serializers.quiz import QuizSerializer, QuizQuestionSerializer
from core.views.template import ListProtectedViewSet
from core.permissions.permissions import QuizPermissions


class QuizViewSet(ListProtectedViewSet):
  """Quizzes: authoring containers of questions, optionally attached to an assignment.

  Attach a quiz to an existing assignment by PATCHing its ``assignment`` field.
  """
  queryset = Quiz.objects.select_related('course', 'assignment', 'createdBy').prefetch_related(
      'quizQuestions__question').all()
  serializer_class = QuizSerializer
  permission_classes = (IsAuthenticated, QuizPermissions)

  @extend_schema(responses=QuizQuestionSerializer(many=True))
  @action(detail=True, methods=['GET'])
  def questions(self, request, pk=None):
    """List this quiz's question memberships, in order."""
    quiz = self.get_object()
    memberships = quiz.quizQuestions.select_related('question').all()
    return Response(QuizQuestionSerializer(memberships, many=True, context={'request': request}).data)
