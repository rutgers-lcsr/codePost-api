# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import SubmissionFile
from core.serializers.file import SubmissionFileSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import FilePermissions


class SubmissionFileViewSet(ListProtectedViewSet):
    """
    ViewSet for SubmissionFile objects.
    
    SubmissionFiles are files that belong to student submissions.
    These were previously just called "File" objects.
    
    list:
    Return a list of all submission files.

    create:
    Create a new submission file.

    retrieve:
    Return the given submission file.

    update:
    Update a submission file.

    partial_update:
    Partially update a submission file.

    delete:
    Delete a submission file.
    """
    queryset = SubmissionFile.objects.all()
    serializer_class = SubmissionFileSerializer
    permission_classes = (IsAuthenticated, FilePermissions)

    def get_serializer_class(self):
        """
        Use simplified serializer for student uploads if needed.
        """
        # You can add logic here to use SubmissionFileStudentUploadSerializer
        # based on user permissions
        return self.serializer_class
