# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Permission classes for codePost API.

This module defines permissions for all major models in the codePost system.
Permissions are organized by domain area for easier navigation and maintenance.

Reference: https://stackoverflow.com/questions/36553197/permission-checks-in-drf-viewsets-are-not-working-right
"""

from core.models import Assignment, AssignmentFile, CourseFile, SubmissionFile, SubmissionTest, User
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
from rest_framework.request import Request
from codepost.settings import logger
from typing import cast

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _is_safe_method(method):
    """Check if HTTP method is safe (GET, HEAD, OPTIONS)."""
    return method in ['GET', 'HEAD', 'OPTIONS']


def _is_write_method(method):
    """Check if HTTP method is a write operation (POST, PUT, PATCH)."""
    return method in ['POST', 'PUT', 'PATCH']


# =============================================================================
# USER & ORGANIZATION PERMISSIONS
# =============================================================================


class OrganizationPermissions(TemplatePermission):
    """
    Permissions for Organization objects.
    
    - Only superusers can create, modify, or view organizations
    - DELETE is disabled to prevent catastrophic cascade effects
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)

        # DELETE is prohibited - use terminal/admin console only
        if request.method == "DELETE":
            return False

        # All other operations require superuser
        if request.method == "GET":
             return user.is_superuser or (user.profile.isOrgStaff and user.profile.organization == obj)

        return user.is_superuser


class UserPermissions(TemplatePermission):
    """
    Permissions for User objects.
    
    - Only superusers can create or modify users
    - Users can view their own profile
    - DELETE is disabled to prevent catastrophic cascade effects
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)

        # DELETE is prohibited - use terminal/admin console only
        if request.method == "DELETE":
            return False

        # GET: superuser or viewing own profile
        if request.method == "GET":
            return user.is_superuser or user == obj

        # POST, PUT, PATCH: superuser only
        return user.is_superuser


class CoursePermissions(TemplatePermission):
    """
    Permissions for Course objects.
    
    - POST: Organization members with course creation privilege
    - GET: Superuser or course members
    - PUT/PATCH: Course admins only
    - DELETE: Prohibited (use terminal/admin console)
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        course = obj

        # DELETE is prohibited - use terminal/admin console only
        if request.method == "DELETE":
            return False

        # GET: superuser or course member
        if request.method == "GET":
            return user.is_superuser or isCourseMember(user, course) or (user.profile.isOrgStaff and user.profile.organization == course.organization)

        # POST: organization member with course creation privilege
        if request.method == "POST":
            return user.is_superuser or (isOrganizationMember(user, course.organization) and hasCourseCreationPrivilege(user))

        # PUT/PATCH: course admin or Org Staff
        if request.method in ["PATCH", "PUT"]:
            return isCourseAdmin(user, course) or (user.profile.isOrgStaff and user.profile.organization == course.organization)

        return False


class BillingPermissions(permissions.BasePermission):
    """
    Permissions for billing operations.
    
    - Authenticated users can access billing actions
    - Course admins can perform billing operations on their courses
    """

    def has_permission(self, request, view):
        if getattr(view, 'action', None) in ['create_checkout_session', 'details', 'request_waiver']:
            return isAuthenticated(request.user)
        return False

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        if getattr(view, 'action', None) in ['create_checkout_session', 'details', 'request_waiver']:
            return isAuthenticated(user) and isCourseAdmin(user, obj)
        return False


# =============================================================================
# COURSE STRUCTURE PERMISSIONS (Sections, Assignments, Rubrics)
# =============================================================================


class SectionPermissions(TemplatePermission):
    """
    Permissions for Section objects.
    
    - POST/PUT/PATCH/DELETE: Course admins only
    - GET: Superuser or course staff
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        course = obj.course

        # GET: superuser or course staff
        if request.method == "GET":
            return user.is_superuser or isCourseStaff(user, course)

        # All write operations: course admin only
        return isCourseAdmin(user, course)


class AssignmentPermissions(TemplatePermission):
    """
    Permissions for Assignment objects.
    
    - POST/PUT/PATCH/DELETE: Course admins only
    - GET: Superuser, course staff, or students (if assignment is visible)
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        course = obj.course

        # GET: superuser, course staff, or course members (if visible)
        if request.method == "GET":
            return (
                user.is_superuser
                or isCourseStaff(user, course)
                or (obj.isVisible and isCourseMember(user, course))
            )

        # All write operations: course admin only
        return isCourseAdmin(user, course)


class RubricCategoryPermissions(TemplatePermission):
    """
    Permissions for RubricCategory objects.
    
    Write permissions depend on collaborativeRubricMode:
    - Collaborative mode: All course staff can modify
    - Standard mode: Only course admins can modify
    
    Read permissions:
    - Superuser or course staff can always view
    - Students can view if assignment is released or in live feedback mode
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        assignment = obj.assignment
        course = assignment.course

        # GET: superuser, staff, or students (if released/live feedback)
        if request.method == "GET":
            return (
                user.is_superuser
                or isCourseStaff(user, course)
                or (isStudent(user, course) and (assignment.isReleased or assignment.liveFeedbackMode))
            )

        # Write operations: depends on collaborative mode
        if assignment.collaborativeRubricMode:
            return isCourseStaff(user, course)
        else:
            from core.permissions.helpers import isRubricEditor
            return isCourseAdmin(user, course) or isRubricEditor(user, course)


class RubricCommentPermissions(TemplatePermission):
    """
    Permissions for RubricComment objects.
    
    Similar to RubricCategory, permissions depend on collaborativeRubricMode:
    - Collaborative mode: All course staff can modify
    - Standard mode: Only course admins can modify
    
    Read permissions:
    - Superuser or course staff can always view
    - Students can view if assignment is released or in live feedback mode
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)

        # Handle both Assignment objects and RubricComment objects
        if type(obj) == Assignment:
            assignment = obj
            course = assignment.course
        else:
            assignment = obj.category.assignment
            course = assignment.course

        # GET: superuser, staff, or students (if released/live feedback)
        if request.method == "GET":
            return (
                user.is_superuser
                or isCourseStaff(user, course)
                or (isStudent(user, course) and (assignment.feedbackReleased or assignment.liveFeedbackMode))
            )

        # Write operations: depends on collaborative mode
        if assignment.collaborativeRubricMode:
            return isCourseStaff(user, course)
        else:
            from core.permissions.helpers import isRubricEditor
            return isCourseAdmin(user, course) or isRubricEditor(user, course)


# =============================================================================
# SUBMISSION & FILE PERMISSIONS
# =============================================================================


class SubmissionPermissions(TemplatePermission):
    """
    Permissions for Submission objects.
    
    - POST/DELETE: Course admins only
    - PUT/PATCH: Course admins or staff assigned to submission
    - GET: Staff of submission, or students (if assignment released/live feedback)
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        course = obj.assignment.course
        assignment = obj.assignment

        # GET: staff of submission, or students (if released/live feedback)
        if request.method == "GET":
            return (
                isStaffOfSub(user, obj)
                or isStudentOfSub(user, obj)
            )

        # PUT/PATCH: course admin or staff of submission
        if request.method in ["PUT", "PATCH"]:
            return isCourseAdmin(user, course) or isStaffOfSub(user, obj)

        # POST/DELETE: course admin only
        return isCourseAdmin(user, course)


class FileTemplatePermissions(TemplatePermission):
    """
    Permissions for FileTemplate objects.
    
    - POST/PUT/PATCH/DELETE: Course admins only
    - GET: All course members
    """

    def has_object_permission(self, request, view, obj):
        raise NotImplementedError("FileTemplatePermissions is deprecated. Use specific file permissions instead.")
        


class FilePermissions(TemplatePermission):
    """
    Permissions for File objects.
    
    Inherits permission logic from parent depending on the type of file.
    """

    def has_object_permission(self, request, view, obj):
      logger.debug(f"FilePermissions: Checking permissions for File object ({obj.id}) of type {type(obj)}")
      
      # Handle polymorphic file types - check for child model attributes
      # Django MTI may pass the base File object, so we need to check for the child model relationship
      # Check in order: SubmissionFile, AssignmentFile, CourseFile
      # Note: Must check child model name (lowercase), not foreign key field names
      
      # Check if it's a SubmissionFile
      if isinstance(obj, SubmissionFile) or hasattr(obj, 'submissionfile'):
        try:
          submission_file = obj if isinstance(obj, SubmissionFile) else obj.submissionfile
          logger.debug(f"FilePermissions: Delegating to SubmissionPermissions for submission {submission_file.submission.id}")
          return SubmissionPermissions().has_object_permission(request, view, submission_file.submission)
        except AttributeError as e:
          logger.warning(f"FilePermissions: Failed to access submissionfile for File {obj.id}: {e}")
          return False
      
      # Check if it's an AssignmentFile
      if isinstance(obj, AssignmentFile) or hasattr(obj, 'assignmentfile'):
        try:
          assignment_file = obj if isinstance(obj, AssignmentFile) else obj.assignmentfile
          logger.debug(f"FilePermissions: Delegating to AssignmentPermissions for assignment {assignment_file.assignment.id}")
          return AssignmentPermissions().has_object_permission(request, view, assignment_file.assignment)
        except AttributeError as e:
          logger.warning(f"FilePermissions: Failed to access assignmentfile for File {obj.id}: {e}")
          return False
      
      # Check if it's a CourseFile
      if isinstance(obj, CourseFile) or hasattr(obj, 'coursefile'):
        try:
          course_file = obj if isinstance(obj, CourseFile) else obj.coursefile
          logger.debug(f"FilePermissions: Delegating to CourseFilePermissions for course {course_file.course.id}")
          return CourseFilePermissions().has_object_permission(request, view, course_file.course)
        except AttributeError as e:
          logger.warning(f"FilePermissions: Failed to access coursefile for File {obj.id}: {e}")
          return False
      
      # If we can't determine the file type, deny access
      logger.error(f"FilePermissions: Could not determine file type for File {obj.id}. No child model found.")
      return False

class CourseFilePermissions(TemplatePermission):
    """
    Permissions for CourseFile objects.
    
    - POST/PUT/PATCH/DELETE: Course admins only
    - GET: Superuser or course members
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        course = obj

        # GET: superuser or course member
        if request.method == "GET":
            return user.is_superuser or isCourseMember(user, course)

        # All write operations: course admin only
        return isCourseAdmin(user, course)


class FileExecutionPermissions(TemplatePermission):
    """
    Permissions for FileExecution on Files. 
    
    If the file is a SubmissionFile, the user must be the submitter, or a staff member of the course the submission belongs to.
    If the file is an AssignmentFile, the user must be a staff member of the course the assignment belongs to.
    If the file is a CourseFile, the user must be a staff member of the course the file belongs to.
    
    Note: This is different then the File Permissions because its for executing files, not viewing them. Students can view CourseFiles, but cannot execute them. Students can only exeute their own files, but they can only get a result if the result has been cached by a StaffofSubmission. Execution should check if the current user is a student of the submission as well. If the user is a student of the submission, they should be able to execute the file, but only if the result has been cached by a StaffofSubmission. If the user is a staff of the submission, they should be able to execute the file and get a result.

    """
    
    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        if isinstance(obj, SubmissionFile) or hasattr(obj, 'submissionfile'):
            submission = obj if isinstance(obj, SubmissionFile) else obj.submissionfile.submission
            
            # Staff can always execute
            if isStaffOfSub(user, submission):
                return True
                
            # Students can execute (view cache) if they are on the submission
            if isStudentOfSub(user, submission):
                return True
                
            return False
        elif isinstance(obj, AssignmentFile) or hasattr(obj, 'assignmentfile'):
            assignment = obj if isinstance(obj, AssignmentFile) else obj.assignmentfile.assignment
            return isCourseStaff(user, assignment.course)
        elif isinstance(obj, CourseFile) or hasattr(obj, 'coursefile'):
            course = obj if isinstance(obj, CourseFile) else obj.coursefile.course
            return isCourseStaff(user, course)
        return False
    

class CommentPermissions(TemplatePermission):
    """
    Permissions for Comment objects.
    Note: Staff are defined as graders, super graders, or course admins.
    
    - POST/PUT/PATCH/DELETE: Staff assigned to submission
    - GET: Inherits from submission permissions
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        submission = obj.file.submission

        # GET: inherit submission permissions
        if request.method == "GET":
            # For comments, we don't just inherit submission permissions because submissions are now always visible to students.
            # We must explicitly check if feedback is released.
            
            # Staff of submission can always view
            if isStaffOfSub(user, submission):
                return True

            # Students can view ONLY if feedback is released or live feedback mode is on
            assignment = submission.assignment
            if isStudentOfSub(user, submission):
                return assignment.feedbackReleased or assignment.liveFeedbackMode
            
            return False

        # All write operations: staff of submission only
        return isStaffOfSub(user, submission)


# =============================================================================
# AUTOGRADER PERMISSIONS (Test Cases, Test Categories, Submission Tests)
# =============================================================================


class TestCasePermissions(TemplatePermission):
    """
    Permissions for TestCase objects.
    
    - POST/PUT/PATCH/DELETE: Course admins only
    - GET: Course staff
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        course = obj.testCategory.assignment.course

        # GET: course staff
        if request.method == "GET":
            return isCourseStaff(user, course)

        # All write operations: course admin only
        return isCourseAdmin(user, course)


class TestCategoryPermissions(TemplatePermission):
    """
    Permissions for TestCategory objects.
    
    - POST/PUT/PATCH/DELETE: Course admins only
    - GET: Course staff
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        course = obj.assignment.course

        # GET: course staff
        if request.method == "GET":
            return isCourseStaff(user, course)

        # All write operations: course admin only
        return isCourseAdmin(user, course)


class TestCategoryResourcePermissions(TemplatePermission):
    """
    Permissions for TestCategoryResource objects.
    
    - POST/PUT/PATCH/DELETE: Course admins only
    - GET: Course staff
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        course = obj.category.assignment.course

        # GET: course staff
        if request.method == "GET":
            return isCourseStaff(user, course)

        # All write operations: course admin only
        return isCourseAdmin(user, course)


class SubmissionTestPermissions(TemplatePermission):
    """
    Permissions for SubmissionTest objects.
    
    - POST/DELETE: Course admins only
    - PUT/PATCH: Course admins or staff of submission
    - GET: Staff of submission, or students of the submission
    """

    def has_object_permission(self, request, view, obj: SubmissionTest):
        user = cast(User, request.user)
        submission = obj.submission
        assignment = submission.assignment
        course = assignment.course

        # GET: staff of submission, or students of the submission
        if request.method == "GET":
            if isStaffOfSub(user, submission):
                return True
            if isStudentOfSub(user, submission):
                return True
            return False

        # PUT/PATCH: course admin or staff of submission
        if request.method in ["PUT", "PATCH"]:
            return isCourseAdmin(user, course) or isStaffOfSub(user, submission)

        # POST/DELETE: course admin only
        return isCourseAdmin(user, course)


# =============================================================================
# AI GRADING ASSISTANCE PERMISSIONS
# =============================================================================


class SuggestedCommentPermissions(TemplatePermission):
    """
    Permissions for SuggestedComment objects.
    Only staff of the submission can view or act on suggested comments.
    Students never see these.
    """

    def has_permission(self, request, view):
        # Skip POST-check for detail actions (accept/reject) — they operate
        # on existing objects and permission is checked in has_object_permission.
        if request.method == 'POST' and view.action in ('accept', 'reject'):
            return True
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        submission = obj.submission
        return isStaffOfSub(user, submission)


class SubmissionSummaryPermissions(TemplatePermission):
    """
    Permissions for SubmissionSummary objects.
    Only staff of the submission can view the summary.
    Students never see these.
    """

    def has_object_permission(self, request, view, obj):
        user = cast(User, request.user)
        submission = obj.submission
        return isStaffOfSub(user, submission)
