# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.permissions import IsAuthenticated

from core.models import QuizQuestion
from core.serializers.quiz import QuizQuestionSerializer
from core.views.template import ListProtectedViewSet
from core.permissions.permissions import QuizQuestionPermissions


class QuizQuestionViewSet(ListProtectedViewSet):
  """Add/remove/reorder a Question within a Quiz. POST to add (with quiz + question),
  PATCH ``sortKey``/``pointsOverride`` to reorder/override, DELETE to remove."""
  queryset = QuizQuestion.objects.select_related('quiz', 'quiz__course', 'question').all()
  serializer_class = QuizQuestionSerializer
  permission_classes = (IsAuthenticated, QuizQuestionPermissions)
