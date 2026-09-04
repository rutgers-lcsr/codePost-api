# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Course-scope helpers for credentials that are pinned to a single course.

Cross-course isolation is enforced by each viewset's ``TemplatePermission``
subclass: a course API key authenticates as the ``course-<id>-api`` service
account, which is a ``courseAdmin`` of exactly one course, so every membership
check fails for any other course.  This module only exposes the scope id so
views can *adjust* behaviour for scoped callers (e.g. hiding capabilities that
make no sense for a course-pinned credential).
"""


def get_course_scope_id(request):
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
