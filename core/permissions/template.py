# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from abc import abstractmethod
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView
from typing import Any


class TemplatePermission(permissions.BasePermission):

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
