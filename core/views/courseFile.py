# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
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
    Return a list of all course files for a given course (requires ?course=<id> parameter).

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
    
    def list(self, request):
        """
        List course files. Requires ?course=<id> query parameter.
        Returns files for courses where the user is a member.
        """
        from core.permissions.helpers import isAuthenticated, isCourseMember
        from core.views.template import returnNotAuthorized, returnForbidden
        from core.models import Course
        from rest_framework.response import Response
        
        user = request.user
        
        if not isAuthenticated(user):
            return returnNotAuthorized()
        
        # Get course ID from query parameters
        course_id = request.query_params.get('course')
        if not course_id:
            return returnForbidden()
        
        try:
            course = Course.objects.get(id=int(course_id))
        except (Course.DoesNotExist, ValueError):
            return returnForbidden()
        
        # Check if user is a member of the course
        if not (user.is_superuser or isCourseMember(user, course)):
            return returnForbidden()
        
        # Filter course files by course
        queryset = self.get_queryset().filter(course=course)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
