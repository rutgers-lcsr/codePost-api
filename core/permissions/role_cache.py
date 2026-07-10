# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Per-request memoization for role-check helpers.

The capability compute chain (course → assignment → submission) calls the same
role helpers (``isCourseAdmin``, ``isGrader``, ``isStaffOfSub``, etc.) multiple
times within a single request.  Each call hits the DB.  This module provides a
thin cache that deduplicates those queries for the duration of one request.

Usage::

    from core.permissions.role_cache import RoleCache

    cache = RoleCache(user)
    cache.is_course_admin(course)   # DB hit the first time
    cache.is_course_admin(course)   # returns cached result

The cache never outlives the request — callers create it on the stack and pass
it through the compute functions.  No thread-local or middleware is involved.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from core.models import Course, Submission


class RoleCache:
    """Memoizes role checks for a single ``(user, course/submission)`` scope.

    All methods are idempotent: multiple calls with the same arguments return
    the first result without hitting the DB again.
    """

    def __init__(self, user: "User") -> None:
        self.user = user
        self._cache: dict[tuple, bool] = {}

    def _key(self, fn_name: str, *args: object) -> tuple:
        return (fn_name, *(id(a) for a in args))

    def _get_or_compute(self, fn_name: str, fn, *args: object) -> bool:
        key = self._key(fn_name, *args)
        if key not in self._cache:
            self._cache[key] = fn(self.user, *args)
        return self._cache[key]

    # -- Course-level helpers --

    def is_student(self, course: "Course") -> bool:
        from core.permissions.helpers import isStudent
        return self._get_or_compute("isStudent", isStudent, course)

    def is_grader(self, course: "Course") -> bool:
        from core.permissions.helpers import isGrader
        return self._get_or_compute("isGrader", isGrader, course)

    def is_super_grader(self, course: "Course") -> bool:
        from core.permissions.helpers import isSuperGrader
        return self._get_or_compute("isSuperGrader", isSuperGrader, course)

    def is_rubric_editor(self, course: "Course") -> bool:
        from core.permissions.helpers import isRubricEditor
        return self._get_or_compute("isRubricEditor", isRubricEditor, course)

    def is_quiz_grader(self, course: "Course") -> bool:
        from core.permissions.helpers import isQuizGrader
        return self._get_or_compute("isQuizGrader", isQuizGrader, course)

    def is_course_admin(self, course: "Course") -> bool:
        from core.permissions.helpers import isCourseAdmin
        return self._get_or_compute("isCourseAdmin", isCourseAdmin, course)

    def is_course_staff(self, course: "Course") -> bool:
        from core.permissions.helpers import isCourseStaff
        return self._get_or_compute("isCourseStaff", isCourseStaff, course)

    def is_course_member(self, course: "Course") -> bool:
        from core.permissions.helpers import isCourseMember
        return self._get_or_compute("isCourseMember", isCourseMember, course)

    # -- Submission-level helpers --

    def is_staff_of_sub(self, submission: "Submission") -> bool:
        from core.permissions.helpers import isStaffOfSub
        return self._get_or_compute("isStaffOfSub", isStaffOfSub, submission)

    def is_student_of_sub(self, submission: "Submission") -> bool:
        from core.permissions.helpers import isStudentOfSub
        return self._get_or_compute("isStudentOfSub", isStudentOfSub, submission)

    # -- Other helpers --

    def can_view_unanonymized_submissions(self, course: "Course") -> bool:
        from core.permissions.helpers import canViewUnanonymizedSubmissions
        return self._get_or_compute("canViewUnanonymized", canViewUnanonymizedSubmissions, course)
