from core.models import AssignmentFile
from core.serializers.file import AssignmentFileSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import FilePermissions


class AssignmentFileViewSet(ListProtectedViewSet):
    """
    ViewSet for AssignmentFile objects.
    
    AssignmentFiles are files that belong to assignments
    (e.g., starter code, instructions, templates, etc.).
    
    list:
    Return a list of all assignment files.

    create:
    Create a new assignment file.

    retrieve:
    Return the given assignment file.

    update:
    Update an assignment file.

    partial_update:
    Partially update an assignment file.

    delete:
    Delete an assignment file.
    """
    queryset = AssignmentFile.objects.all()
    serializer_class = AssignmentFileSerializer
    permission_classes = (IsAuthenticated, FilePermissions)
