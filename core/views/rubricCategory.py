# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import RubricCategory
from core.serializers.rubricCategory import RubricCategorySerializer, RubricCategoryStudentSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import RubricCategoryPermissions
from core.permissions.helpers import isCourseStaff

class RubricCategoryViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the rubric categories.

  create:
  Create a new rubric category.

  retrieve:
  Return the given rubric category.

  update:
  Update a rubric category.

  partial_update:
  Update a rubric category.

  delete:
  Delete a rubric category.
  """
  queryset = RubricCategory.objects.all()
  serializer_class = RubricCategorySerializer
  permission_classes = (IsAuthenticated, RubricCategoryPermissions)

  def get_serializer_class(self):
    # During schema generation, return default serializer
    if getattr(self, 'swagger_fake_view', False):
        return RubricCategorySerializer
        
    if self.action == 'retrieve':
      user = self.request.user
      rubricCategory = self.get_object()
      course = rubricCategory.assignment.course
      if isCourseStaff(user, course):
        return RubricCategorySerializer
      else:
        return RubricCategoryStudentSerializer
    else:
        return RubricCategorySerializer