from core.models import SolutionFile
from autograder.serializers.solutionFile import SolutionFileSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from autograder.permissions.permissions import SolutionFilePermissions
from autograder.testUtils.logging import standardLog
from rest_framework.response import Response
from rest_framework import status


class SolutionFileViewSet(ListProtectedViewSet):
    """
    list:
    Return a list of all the testFiles.

    create:
    Create a new testFile.

    retrieve:
    Return the given testFile.

    update:
    Update a testFile.

    partial_update:
    Update a testFile.

    delete:
    Delete a testFile.
    """

    queryset = SolutionFile.objects.all()
    serializer_class = SolutionFileSerializer
    permission_classes = (IsAuthenticated, SolutionFilePermissions)

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            standardLog(
                request.user,
                "Error: SolutionFile upload error | " + request.data["name"],
                str(e),
                "#user_notifications_uploads",
            )
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )
