from core.models import FileTemplate
from core.serializers.fileTemplate import FileTemplateSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import FileTemplatePermissions


class FileTemplateViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the file templates.

  create:
  Create a new file template.

  retrieve:
  Return the given file template.

  update:
  Update a file template.

  partial_update:
  Update a file template.

  delete:
  Delete a file template.
  """
  queryset = FileTemplate.objects.all()
  serializer_class = FileTemplateSerializer
  permission_classes = (IsAuthenticated, FileTemplatePermissions)
