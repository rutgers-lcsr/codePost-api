# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from core.models import QuizSuggestionJob
from core.serializers.quizSuggestionJob import QuizSuggestionJobSerializer
from core.permissions.permissions import QuizSuggestionJobPermissions


class QuizSuggestionJobViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
  """Poll an AI quiz-suggestion generation run.

  Jobs are created by ``assignments/{id}/generateQuizQuestions/`` and
  ``questions/{id}/regenerateSuggestion/``; the generation task updates
  ``status``/``errorMessage``/``createdCount`` on every exit path, so clients
  poll here instead of inferring failure from an empty suggestion list.

  retrieve:
  Return the generation run's current status, suggestion count, and error detail.
  """
  queryset = QuizSuggestionJob.objects.select_related('course', 'assignment', 'sourceQuestion').all()
  serializer_class = QuizSuggestionJobSerializer
  permission_classes = (IsAuthenticated, QuizSuggestionJobPermissions)
