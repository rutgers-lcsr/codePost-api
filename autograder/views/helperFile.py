from core.models import HelperFile
from autograder.serializers.helperFile import HelperFileSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from autograder.permissions.permissions import HelperFilePermissions
from autograder.testUtils.logging import standardLog
from rest_framework.response import Response
from rest_framework import status


class HelperFileViewSet(ListProtectedViewSet):
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

    queryset = HelperFile.objects.all()
    serializer_class = HelperFileSerializer
    permission_classes = (IsAuthenticated, HelperFilePermissions)

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            standardLog(
                request.user,
                "Error: HelperFile upload error | " + request.data["name"],
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
