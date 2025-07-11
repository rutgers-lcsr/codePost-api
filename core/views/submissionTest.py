from core.models import SubmissionTest
from core.serializers.submissionTest import SubmissionTestSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import SubmissionTestPermissions

class SubmissionTestViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the solutionFiles.

  create:
  Create a new solutionFiles.

  retrieve:
  Return the given solutionFiles.

  update:
  Update a solutionFiles.

  partial_update:
  Update a solutionFiles.

  delete:
  Delete a solutionFiles.
  """
  queryset = SubmissionTest.objects.all()
  serializer_class = SubmissionTestSerializer
  permission_classes = (IsAuthenticated, SubmissionTestPermissions)
