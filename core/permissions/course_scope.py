# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import permissions

from core.models import Course


def _get_course_scope_id(request):
    """Extract the course scope ID from ``request.auth``, if present.

    Returns ``None`` when the request is not course-scoped.
    """
    auth = getattr(request, "auth", None)
    if auth is None:
        return None

    # Dict-style auth info from CourseAPIKeyAuthentication or CourseScopedTokenInfo
    if isinstance(auth, dict):
        return auth.get("course_scope_id")
    return getattr(auth, "course_scope_id", None)


def _resolve_course_id(obj):
    """Walk the object's relationships to find the owning Course id.

    Returns ``None`` if the object has no discernible course link.
    """
    if isinstance(obj, Course):
        return obj.pk

    # Direct FK named ``course`` (Assignment, Section, CourseFile, etc.)
    course = getattr(obj, "course", None)
    if course is not None:
        return course.pk if hasattr(course, "pk") else course

    # Models that expose get_course() (File subclasses)
    if hasattr(obj, "get_course"):
        c = obj.get_course()
        return c.pk if c else None

    # Submission → assignment → course
    assignment = getattr(obj, "assignment", None)
    if assignment is not None:
        course = getattr(assignment, "course", None)
        if course is not None:
            return course.pk if hasattr(course, "pk") else course

    # RubricComment → category → assignment → course
    category = getattr(obj, "category", None)
    if category is not None:
        assignment = getattr(category, "assignment", None)
        if assignment is not None:
            course = getattr(assignment, "course", None)
            if course is not None:
                return course.pk if hasattr(course, "pk") else course

    # Comment → file → submission → assignment → course
    file_obj = getattr(obj, "file", None)
    if file_obj is not None:
        if hasattr(file_obj, "get_course"):
            c = file_obj.get_course()
            return c.pk if c else None

    # TestCase → testCategory → assignment → course
    test_category = getattr(obj, "testCategory", None)
    if test_category is not None:
        assignment = getattr(test_category, "assignment", None)
        if assignment is not None:
            course = getattr(assignment, "course", None)
            if course is not None:
                return course.pk if hasattr(course, "pk") else course

    return None


class CourseScopePermission(permissions.BasePermission):
    """Deny access when the request is course-scoped and the target
    resource belongs to a different course.

    Requests that are **not** course-scoped pass through unconditionally
    so existing behaviour is preserved.
    """

    message = "This API key is scoped to a different course."

    def has_permission(self, request, view):
        scope_id = _get_course_scope_id(request)
        if scope_id is None:
            return True

        # Stash on request for downstream consumers (views, other permissions)
        request.course_scope_id = scope_id

        # For object-level endpoints the real check happens in has_object_permission.
        # For list/create we try to infer the course from query params or POST data.
        course_param = (
            request.query_params.get("course")
            or request.data.get("course")
            or request.data.get("courseId")
        )
        if course_param is not None:
            try:
                if int(course_param) != int(scope_id):
                    return False
            except (ValueError, TypeError):
                return False

        return True

    def has_object_permission(self, request, view, obj):
        scope_id = _get_course_scope_id(request)
        if scope_id is None:
            return True

        obj_course_id = _resolve_course_id(obj)
        if obj_course_id is None:
            # Cannot determine course — play it safe and deny.
            # Exception: User objects for the authenticated user themselves
            from django.contrib.auth.models import User
            if isinstance(obj, User) and obj.pk == request.user.pk:
                return True
            return False

        return int(obj_course_id) == int(scope_id)
