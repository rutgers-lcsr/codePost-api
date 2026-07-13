# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.permissions import IsAuthenticated

from core.models import QuizQuestionGroup
from core.serializers.quizQuestionGroup import QuizQuestionGroupSerializer
from core.views.template import ListProtectedViewSet
from core.permissions.permissions import QuizQuestionGroupPermissions


class QuizQuestionGroupViewSet(ListProtectedViewSet):
  """Random-draw groups on a quiz: pick N random questions from a bank, P points each.
  POST to add (with quiz + bank + pickCount + pointsPerQuestion), PATCH to edit, DELETE to remove."""
  queryset = QuizQuestionGroup.objects.select_related('quiz', 'quiz__course', 'bank').all()
  serializer_class = QuizQuestionGroupSerializer
  permission_classes = (IsAuthenticated, QuizQuestionGroupPermissions)
