# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.

from core.permissions.template import TemplatePermission
from core.permissions.helpers import isGrader, isCourseAdmin

class SolutionFilePermissions(TemplatePermission):
  def has_object_permission(self, request, view, obj):
    user = request.user
    course = obj.environment.assignment.course

    if request.method == "POST":
      return isCourseAdmin(user, course)
    if request.method == "DELETE":
      return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      return isCourseAdmin(user, course)
    if request.method == "GET":
      return isCourseAdmin(user, course)

class HelperFilePermissions(TemplatePermission):
  def has_object_permission(self, request, view, obj):
    user = request.user
    course = obj.environment.assignment.course

    if request.method == "POST":
      return isCourseAdmin(user, course)
    if request.method == "DELETE":
      return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      return isCourseAdmin(user, course)
    if request.method == "GET":
      return isCourseAdmin(user, course)




class EnvironmentPermissions(TemplatePermission):
  def has_object_permission(self, request, view, obj):
    user = request.user
    course = obj.assignment.course

    if request.method == "POST":
      return isCourseAdmin(user, course)
    if request.method == "DELETE":
      return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      return isCourseAdmin(user, course)
    if request.method == "GET":
      return isCourseAdmin(user, course) or isGrader(user, course)
