from rest_framework import permissions

from core.permissions.template import TemplatePermission
from core.permissions.helpers import isAuthenticated

from core.models import Course
from core.permissions.helpers import isGrader

from core.utils import get_mooc_courses


class ProductPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user

    if request.method == "POST":
      return False
    if request.method == "DELETE":
      return False
    if request.method == "PATCH" or request.method == "PUT":
      return False
    if request.method == "GET":
      return True

class TierPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user

    if request.method == "POST":
      return False
    if request.method == "DELETE":
      return False
    if request.method == "PATCH" or request.method == "PUT":
      return False
    if request.method == "GET":
      return True


class OrderPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user

    if request.method == "POST":
      return True
    if request.method == "DELETE":
      return False
    if request.method == "PATCH" or request.method == "PUT":
      return False
    if request.method == "GET":
      return False


class CreditPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    credit = obj

    if request.method == "POST":
      return False
    if request.method == "DELETE":
      return False
    if request.method == "PATCH" or request.method == "PUT":
      return credit.user == user
    if request.method == "GET":
      if not credit:
        return True
      else:
        return credit.user == user


class ReviewPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    review = obj

    # course = review.credit.order.product.course

    if request.method == "POST":
      return False
    if request.method == "DELETE":
      return False
    if request.method == "PATCH" or request.method == "PUT":
      return False
    if request.method == "GET":
      if not review:
        return False
      else:
        return review.reviewer == user


class PayoutPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    payout = obj

    is_mooc_grader = False
    for course_id in get_mooc_courses():
      course = Course.objects.get(id=course_id)
      if isGrader(user, course):
        is_mooc_grader = True

    if request.method == "POST":
      return is_mooc_grader
    if request.method == "DELETE":
      return False
    if request.method == "PATCH" or request.method == "PUT":
      return False
    if request.method == "GET":
      if not payout:
        return True
      else:
        return payout.reviewer == user
