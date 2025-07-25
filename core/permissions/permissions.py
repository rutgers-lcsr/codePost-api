from core.models import Assignment
from core.permissions.helpers import (
  hasCourseCreationPrivilege,
  isAuthenticated,
  isCourseAdmin,
  isCourseMember,
  isCourseStaff,
  isOrganizationMember,
  isStaffOfSub,
  isStudent,
  isStudentOfSub,
)
from core.permissions.template import TemplatePermission
from rest_framework import permissions

# Notes
# https://stackoverflow.com/questions/36553197/permission-checks-in-drf-viewsets-are-not-working-right

############# User Section ####################################################


class OrganizationPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user

    if request.method == "POST":
      return user.is_superuser
    if request.method == "DELETE":
      # Since deleting an organization can have catastrophic cascade effects,
      # we should only allow deletion of an organization object from the terminal.
      # Maybe we can protect it with a confirm pattern.
      return False
    if request.method == "PATCH" or request.method == "PUT":
      return user.is_superuser
    if request.method == "GET":
      return user.is_superuser


class UserPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user

    if request.method == "POST":
      return user.is_superuser
    if request.method == "DELETE":
      # Since deleting a user can have catastrophic cascade effects,
      # we should only allow deletion of an user object from the terminal.
      # Maybe we can protect it with a confirm pattern.
      return False
    if request.method == "PATCH" or request.method == "PUT":
      return user.is_superuser
    if request.method == "GET":
      return user.is_superuser or user == obj


class CoursePermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    course = obj

    if request.method == "POST":
      return isOrganizationMember(user, course.organization) and hasCourseCreationPrivilege(user)
    if request.method == "DELETE":
      # Since deleting a course can have catastrophic cascade effects,
      # we should only allow deletion of an course object from the terminal.
      # Maybe we can protect it with a confirm pattern.
      return False
    if request.method == "PATCH" or request.method == "PUT":
      return isCourseAdmin(user, course)
    if request.method == "GET":
      return user.is_superuser or isCourseMember(user, course)

class BillingPermissions(permissions.BasePermission):
  def has_permission(self, request, view):
    if view.action in ['create_checkout_session', 'details', 'request_waiver']:
      return isAuthenticated(request.user)

  def has_object_permission(self, request, view, obj):
    if isAuthenticated(request.user) and  isCourseAdmin(request.user, obj):
      if view.action in ['create_checkout_session', 'details', 'request_waiver']:
        return True
    return False

################################################################################

############# Course Infrastructure Section ####################################


class SectionPermissions(TemplatePermission):

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
      return user.is_superuser or isCourseStaff(user, course)


class AssignmentPermissions(TemplatePermission):

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
      return user.is_superuser or isCourseStaff(user, course) or (obj.isVisible and isCourseMember(user, course))


class RubricCategoryPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    assignment = obj.assignment
    course = obj.assignment.course

    if request.method == "POST":
      if assignment.collaborativeRubricMode:
        return isCourseStaff(user, course)
      else:
        return isCourseAdmin(user, course)
    if request.method == "DELETE":
      if assignment.collaborativeRubricMode:
        return isCourseStaff(user, course)
      else:
        return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      if assignment.collaborativeRubricMode:
        return isCourseStaff(user, course)
      else:
        return isCourseAdmin(user, course)
    if request.method == "GET":
      return user.is_superuser or isCourseStaff(user, course) or (isStudent(user, course) and (obj.assignment.isReleased or obj.assignment.liveFeedbackMode))


class RubricCommentPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user

    if type(obj) == Assignment:
      assignment = obj
      course = assignment.course
    else:
      assignment = obj.category.assignment
      course = obj.category.assignment.course

    def hasLinkedComments(rubricComment):
      return rubricComment.comments.count() > 0

    if request.method == "POST":
      if assignment.collaborativeRubricMode:
        return isCourseStaff(user, course)
      else:
        return isCourseAdmin(user, course)
    if request.method == "DELETE":
      if assignment.collaborativeRubricMode:
        return isCourseStaff(user, course)
      else:
        return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      if assignment.collaborativeRubricMode:
        return isCourseStaff(user, course)
      else:
        return isCourseAdmin(user, course)
    if request.method == "GET":
      return user.is_superuser or isCourseStaff(user, course) or (isStudent(user, course) and (assignment.isReleased or assignment.liveFeedbackMode))

###############################################################################

############# Submissions Section #############################################


class SubmissionPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    course = obj.assignment.course

    if request.method == "POST":
      return isCourseAdmin(user, course)
    if request.method == "DELETE":
      return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      return isCourseAdmin(user, course) or isStaffOfSub(user, obj)
    if request.method == "GET":
      return isStaffOfSub(user, obj) or (isStudentOfSub(user, obj) and (obj.assignment.isReleased or obj.assignment.liveFeedbackMode))


class FileTemplatePermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    assignment = obj.assignment
    course = obj.assignment.course

    if request.method == "POST":
      return isCourseAdmin(user, course)
    if request.method == "DELETE":
      return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      return isCourseAdmin(user, course)
    if request.method == "GET":
      return isCourseMember(user, course)


class FilePermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    return SubmissionPermissions.has_object_permission(self, request, view, obj.submission)


class CommentPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    submission = obj.file.submission

    if request.method == "POST":
      return isStaffOfSub(user, submission)
    if request.method == "DELETE":
      return isStaffOfSub(user, submission)
    if request.method == "PATCH" or request.method == "PUT":
      return isStaffOfSub(user, submission)
    if request.method == "GET":
      return SubmissionPermissions.has_object_permission(self, request, view, submission)

########################## Autograder Models #####################################################


class TestCasePermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    course = obj.testCategory.assignment.course

    if request.method == "POST":
      return isCourseAdmin(user, course)
    if request.method == "DELETE":
      return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      return isCourseAdmin(user, course)
    if request.method == "GET":
      return isCourseStaff(user, course)


class TestCategoryPermissions(TemplatePermission):

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
      return isCourseStaff(user, course)


class SubmissionTestPermissions(TemplatePermission):

  def has_object_permission(self, request, view, obj):
    user = request.user
    course = obj.submission.assignment.course
    assignment = obj.submission.assignment
    submission = obj.submission

    if request.method == "POST":
      return isCourseAdmin(user, course)
    if request.method == "DELETE":
      return isCourseAdmin(user, course)
    if request.method == "PATCH" or request.method == "PUT":
      return isCourseAdmin(user, course) or isStaffOfSub(user, submission)
    if request.method == "GET":
      return isStaffOfSub(user, submission) or (isStudentOfSub(user, submission) and ((assignment.isReleased and submission.isFinalized) or assignment.liveFeedbackMode or (obj.testCase.exposed)))
