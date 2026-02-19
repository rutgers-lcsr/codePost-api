from core.models import AssignmentFile
from core.serializers.file import AssignmentFileSerializer, AssignmentFileSummarySerializer
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
    permission_classes = (IsAuthenticated, FilePermissions)

    def get_serializer_class(self):
        if self.action == 'list':
            return AssignmentFileSummarySerializer
        return AssignmentFileSerializer

    def perform_create(self, serializer):
        instance = serializer.save()
        try:
            from autograder.run import AutoDetectEnvironment
            # Run detection asynchronously with a delay (countdown) to debounce multiple file uploads
            # If 5 files are uploaded, 5 tasks are queued. The first one runs in 2s, sets "Building", 
            # and invalidates the others.
            AutoDetectEnvironment.apply_async(args=[instance.assignment.id], countdown=2)
        except Exception as e:
            print(f"Error in auto-detect: {e}")

    def perform_update(self, serializer):
        instance = serializer.save()
        try:
            from autograder.run import AutoDetectEnvironment
            AutoDetectEnvironment.apply_async(args=[instance.assignment.id], countdown=2)
        except Exception as e:
            print(f"Error in auto-detect: {e}")
