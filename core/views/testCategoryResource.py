# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import TestCategoryResource
from core.serializers.testCategoryResource import TestCategoryResourceSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import TestCategoryResourcePermissions

class TestCategoryResourceViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the testCategoryResources.

  create:
  Create a new testCategoryResource.

  retrieve:
  Return the given testCategoryResource.

  update:
  Update a testCategoryResource.

  partial_update:
  Update a testCategoryResource.

  delete:
  Delete a testCategoryResource.
  """
  queryset = TestCategoryResource.objects.all()
  serializer_class = TestCategoryResourceSerializer
  permission_classes = (IsAuthenticated, TestCategoryResourcePermissions)

