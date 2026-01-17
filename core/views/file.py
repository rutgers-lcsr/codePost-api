from core.models import File, SubmissionFile, AssignmentFile, CourseFile
from core.serializers.file import (
    FileSerializer, 
    SubmissionFileSerializer, 
    AssignmentFileSerializer,
    CourseFileSerializer
)
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import FilePermissions


class FileViewSet(ListProtectedViewSet):
    """
    ViewSet for base File objects.
    
    This handles all file types polymorphically. For specific file types,
    use the dedicated endpoints:
    - /submissionFiles/ for SubmissionFile objects
    - /assignmentFiles/ for AssignmentFile objects
    - /courseFiles/ for CourseFile objects
    
    list:
    Return a list of all files (all types).

    create:
    Create a new file.

    retrieve:
    Return the given file.

    update:
    Update a file.

    partial_update:
    Partially update a file.

    delete:
    Delete a file.
    """
    queryset = File.objects.all()
    serializer_class = FileSerializer
    permission_classes = (IsAuthenticated, FilePermissions)

    def get_serializer_class(self):
        """
        Return appropriate serializer based on the file type.
        """
        # During schema generation, return default serializer
        if getattr(self, 'swagger_fake_view', False):
            return FileSerializer
            
        if self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            # For object-specific actions, use the appropriate serializer
            file_obj = self.get_object()
            if isinstance(file_obj, SubmissionFile):
                return SubmissionFileSerializer
            elif isinstance(file_obj, AssignmentFile):
                return AssignmentFileSerializer
            elif isinstance(file_obj, CourseFile):
                return CourseFileSerializer
        
        if self.action == 'create' and self.request.data:
            if 'submission' in self.request.data:
                return SubmissionFileSerializer
            elif 'assignment' in self.request.data:
                return AssignmentFileSerializer
            elif 'course' in self.request.data:
                return CourseFileSerializer
                
        return self.serializer_class