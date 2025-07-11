from core.models import TestCategory, TestCase, Submission
from core.serializers.testCategory import TestCategorySerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import TestCategoryPermissions

class TestCategoryViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the testCategories.

  create:
  Create a new testCategories.

  retrieve:
  Return the given testCategories.

  update:
  Update a testCategories.

  partial_update:
  Update a testCategories.

  delete:
  Delete a testCategories.
  """
  queryset = TestCategory.objects.all()
  serializer_class = TestCategorySerializer
  permission_classes = (IsAuthenticated, TestCategoryPermissions)
