from core.models import CourseFile
from core.serializers.file import CourseFileSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import FilePermissions


class CourseFileViewSet(ListProtectedViewSet):
    """
    ViewSet for CourseFile objects.
    
    CourseFiles are files that belong to courses
    (e.g., syllabi, course resources, etc.).
    
    list:
    Return a list of all course files.

    create:
    Create a new course file.

    retrieve:
    Return the given course file.

    update:
    Update a course file.

    partial_update:
    Partially update a course file.

    delete:
    Delete a course file.
    """
    queryset = CourseFile.objects.all()
    serializer_class = CourseFileSerializer
    permission_classes = (IsAuthenticated, FilePermissions)
