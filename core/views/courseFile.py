# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import base64
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseNotFound
from django.utils.http import content_disposition_header
from core.models import CourseFile, CourseFileContent
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
        Staff see every file; students only see files flipped to studentVisible.
        """
        from core.permissions.helpers import isAuthenticated, isCourseMember, isCourseStaff
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
        queryset = self.get_queryset().filter(course=course).select_related('content')
        if not (user.is_superuser or isCourseStaff(user, course)):
            queryset = queryset.filter(studentVisible=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


def serve_public_course_file(request, token):
    """Public, unauthenticated download of CourseFile content marked isPublic.

    Plain Django view so it bypasses DRF auth (mirrors serve_quiz_image). The unguessable
    token locates the shared content (courses sharing a file via cloning serve the same
    token; one course unpublishing splits off its own copy rather than 404ing the rest);
    isPublic is the access gate, so non-public (or missing) content returns 404 without
    revealing existence.
    """
    try:
        content = CourseFileContent.objects.get(token=token)
    except (CourseFileContent.DoesNotExist, ValidationError, ValueError):
        return HttpResponseNotFound()
    if not content.isPublic:
        return HttpResponseNotFound()
    # Deterministic download filename: the lowest-id sharing row (the original uploader).
    cf = content.files.order_by('id').first()
    if cf is None:
        return HttpResponseNotFound()  # orphaned content; GC should make this unreachable

    data = content.data or ""
    if data.startswith('data:'):
        # data URI: "data:<mime>;base64,<payload>"
        header, _, encoded = data.partition(',')
        mime = header[len('data:'):].split(';')[0].strip() or 'application/octet-stream'
        try:
            body = base64.b64decode(encoded)
        except Exception:
            return HttpResponseNotFound()
    else:
        mime = 'text/plain; charset=utf-8'
        body = data.encode('utf-8')

    resp = HttpResponse(body, content_type=mime)
    # Force download, never inline: this is arbitrary admin-uploaded content served
    # unauthenticated on the API origin, so rendering (e.g. HTML/SVG) inline would be a
    # stored-XSS vector. attachment + nosniff makes the browser download rather than execute.
    resp['Content-Disposition'] = content_disposition_header(as_attachment=True, filename=cf.name)
    resp['X-Content-Type-Options'] = 'nosniff'
    resp['Cache-Control'] = 'no-cache'  # id-addressed content is mutable, unlike quiz images
    return resp
