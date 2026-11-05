# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from abc import abstractmethod
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import exceptions, permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from typing import Any


# Attribute paths from a model instance to its Course, tried in order.
_COURSE_PATHS = (
  ('course',),
  ('assignment', 'course'),
  ('category', 'assignment', 'course'),
  ('file', 'submission', 'assignment', 'course'),
  ('submission', 'assignment', 'course'),
)


def courseOf(obj):
  '''The Course a model instance belongs to, or None when it has no course (or is a Course).'''
  from core.models import Course
  if isinstance(obj, Course):
    return None
  for path in _COURSE_PATHS:
    target = obj
    try:
      for attr in path:
        target = getattr(target, attr)
    except (AttributeError, ObjectDoesNotExist):
      continue
    if isinstance(target, Course):
      return target
  return None


class TemplatePermission(permissions.BasePermission):

  def __init_subclass__(cls, **kwargs):
    '''
    Archived courses are read-only. Edits are refused by the serializer's validate(), but
    creates (POST) and deletes never reach it, so enforce them here, once, by wrapping each
    subclass's has_object_permission: only after the class has authorized the caller do we
    reveal that the course is archived. The Course itself is exempt so an admin can unarchive it.
    '''
    super().__init_subclass__(**kwargs)
    original = cls.__dict__.get('has_object_permission')
    if original is None:
      return

    def has_object_permission(self, request, view, obj, _original=original):
      allowed = _original(self, request, view, obj)
      # A POST only creates when it is checked against the unsaved instance has_permission
      # builds; detail actions (e.g. assignments/{id}/clone/) get the existing row and only
      # read it, so they are not edits of the archived course.
      creating = request.method == 'POST' and obj.pk is None
      if allowed and (creating or request.method == 'DELETE'):
        course = courseOf(obj)
        if course is not None and course.archived:
          raise exceptions.PermissionDenied("The Course is archived and cannot be edited.")
      return allowed

    cls.has_object_permission = has_object_permission  # type: ignore[method-assign]

  def has_permission(self, request, view):
    if request.method == "POST":
      serializer = view.get_serializer(data=request.data)  # type: ignore[attr-defined]
      if serializer.is_valid(raise_exception=False):
        obj = serializer.createForPOSTCheck()
        return self.has_object_permission(request, view, obj)

    return True

  @abstractmethod
  def has_object_permission(self, request: Request, view: APIView, obj: Any):
    pass


class SuperuserPermission(permissions.BasePermission):

  def has_permission(self, request, view):
    return request.user.is_superuser  # type: ignore[union-attr]
