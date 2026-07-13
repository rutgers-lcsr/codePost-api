# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.models import LearningObjective
from core.serializers.learningObjective import LearningObjectiveSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import LearningObjectivePermissions


class LearningObjectiveViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the learningObjectives.

  create:
  Create a new learningObjective.

  retrieve:
  Return the given learningObjective.

  update:
  Update a learningObjective.

  partial_update:
  Update a learningObjective.

  delete:
  Delete a learningObjective.
  """
  queryset = LearningObjective.objects.all()
  serializer_class = LearningObjectiveSerializer
  permission_classes = (IsAuthenticated, LearningObjectivePermissions)
