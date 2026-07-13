# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

from core.permissions.template import TemplatePermission
from core.permissions.helpers import isCourseAdmin

class WebhookPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    course = obj.course

    if request.method == "POST":
      return isCourseAdmin(user, course)
    if request.method == "DELETE":
      return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      return isCourseAdmin(user, course)
    if request.method == "GET":
      return isCourseAdmin(user, course)
