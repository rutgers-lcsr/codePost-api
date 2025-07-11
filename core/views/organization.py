from core.models import Organization
from core.serializers.organization import OrganizationSerializer
from core.views.template import SuperUserListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import OrganizationPermissions
from rest_framework.decorators import permission_classes


class OrganizationViewSet(SuperUserListProtectedViewSet):
  """
  list:
  Return a list of all the organizations.

  create:
  Create a new organization.

  retrieve:
  Return the given organization.

  update:
  Update an organization.

  partial_update:
  Update an organization.

  delete:
  Delete an organization
  """
  queryset = Organization.objects.all()
  serializer_class = OrganizationSerializer
  permission_classes = (IsAuthenticated, OrganizationPermissions)
