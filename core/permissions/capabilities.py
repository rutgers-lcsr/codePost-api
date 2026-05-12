# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from enum import Enum
from typing import Union

from rest_framework.exceptions import PermissionDenied

from core.permissions.role_cache import RoleCache


class Capability(str, Enum):
    """Granular capabilities for the codePost permission system.

    Each value is a stable key returned in ``capabilities`` API responses
    and used as the canonical identifier in docs and the frontend.
    """

    # -- Course-level --
    VIEW_COURSE = "view_course"
    EDIT_COURSE_SETTINGS = "edit_course_settings"
    MANAGE_ROSTER = "manage_roster"
    VIEW_ROSTER = "view_roster"
    MANAGE_SECTIONS = "manage_sections"
    VIEW_ANALYTICS = "view_analytics"
    CONFIGURE_AI = "configure_ai"
    VIEW_AI_USAGE = "view_ai_usage"
    CREATE_ASSIGNMENT = "create_assignment"
    CLAIM_SUBMISSIONS = "claim_submissions"
    VIEW_AUDIT_LOG = "view_audit_log"
    CHANGE_INVITE_CODE = "change_invite_code"
    MANAGE_COURSE_API_KEYS = "manage_course_api_keys"

    # -- Assignment-level --
    EDIT_ASSIGNMENT = "edit_assignment"
    COPY_ASSIGNMENT = "copy_assignment"
    VIEW_ASSIGNMENT = "view_assignment"
    EDIT_RUBRIC = "edit_rubric"
    VIEW_RUBRIC = "view_rubric"
    RELEASE_GRADES = "release_grades"
    MANAGE_EXTENSIONS = "manage_extensions"
    VIEW_QUEUE = "view_queue"
    MANAGE_TEST_CASES = "manage_test_cases"
    VIEW_ASSIGNMENT_STATISTICS = "view_assignment_statistics"
    UPLOAD_SUBMISSION = "upload_submission"
    GENERATE_AI_TEST_CASES = "generate_ai_test_cases"
    MANAGE_DATASETS = "manage_datasets"
    DOWNLOAD_ASSIGNMENT_FILES = "download_assignment_files"

    # -- Submission-level --
    VIEW_SUBMISSION = "view_submission"
    VIEW_FEEDBACK = "view_feedback"
    GRADE_SUBMISSION = "grade_submission"
    COMMENT_ON_SUBMISSION = "comment_on_submission"
    FINALIZE_SUBMISSION = "finalize_submission"
    UNFINALIZE_SUBMISSION = "unfinalize_submission"
    VIEW_STUDENT_IDENTITY = "view_student_identity"
    REQUEST_REGRADE = "request_regrade"
    MANAGE_REGRADES = "manage_regrades"
    RUN_AUTOGRADER = "run_autograder"
    VIEW_TEST_RESULTS = "view_test_results"
    RUN_CODE = "run_code"
    GENERATE_AI_COMMENTS = "generate_ai_comments"
    MANAGE_PARTNERS = "manage_partners"
    NOTIFY_STUDENTS_FEEDBACK = "notify_students_feedback"
    VIEW_AI_ASSISTANCE = "view_ai_assistance"
    TRIGGER_AI_ASSISTANCE = "trigger_ai_assistance"
    MANAGE_GLOBAL_TEMPLATES = "manage_global_templates"
    VIEW_SUBMISSION_HISTORY = "view_submission_history"
    PROVIDE_COMMENT_FEEDBACK = "provide_comment_feedback"

    # -- Platform-level --
    CREATE_COURSE = "create_course"
    MANAGE_ORGANIZATION = "manage_organization"
    IMPERSONATE_USER = "impersonate_user"
    ACCESS_ADMIN_DASHBOARD = "access_admin_dashboard"


CAPABILITY_DESCRIPTIONS: dict[Capability, str] = {
    # Course
    Capability.VIEW_COURSE: "View the course dashboard and basic course information.",
    Capability.EDIT_COURSE_SETTINGS: "Modify course configuration such as name, period, grading options, and deadlines.",
    Capability.MANAGE_ROSTER: "Add or remove students, graders, and course admins from the course roster.",
    Capability.VIEW_ROSTER: "View the list of students and staff enrolled in the course.",
    Capability.MANAGE_SECTIONS: "Create, edit, or delete sections and assign section leaders.",
    Capability.VIEW_ANALYTICS: "Access course-level analytics, grade distributions, and grading progress dashboards.",
    Capability.CONFIGURE_AI: "Enable, disable, or configure AI-powered feedback settings for the course.",
    Capability.VIEW_AI_USAGE: "View AI credit usage and generation history for the course.",
    Capability.CREATE_ASSIGNMENT: "Create new assignments within the course.",
    Capability.CLAIM_SUBMISSIONS: "Claim ungraded submissions from the grading queue.",
    Capability.VIEW_AUDIT_LOG: "View and export the course-level audit log of student and grader activity.",
    Capability.CHANGE_INVITE_CODE: "Regenerate the course join invite code.",
    Capability.MANAGE_COURSE_API_KEYS: "Create, revoke, and manage course-scoped API keys.",
    # Assignment
    Capability.EDIT_ASSIGNMENT: "Modify assignment settings including name, deadlines, point values, and visibility.",
    Capability.COPY_ASSIGNMENT: "Duplicate an assignment's configuration, rubric, and test cases to another course.",
    Capability.VIEW_ASSIGNMENT: "View the assignment and its associated submissions.",
    Capability.EDIT_RUBRIC: "Create, modify, or delete rubric categories, comments, and point values.",
    Capability.VIEW_RUBRIC: "View the rubric structure and comments.",
    Capability.RELEASE_GRADES: "Toggle feedback release so students can view their grades and comments.",
    Capability.MANAGE_EXTENSIONS: "Grant deadline extensions to individual students or groups.",
    Capability.VIEW_QUEUE: "View the grading queue and assignment completion statistics.",
    Capability.MANAGE_TEST_CASES: "Create, edit, or sync autograder test cases and test categories.",
    Capability.VIEW_ASSIGNMENT_STATISTICS: "View detailed grade distributions and grading statistics for an assignment.",
    Capability.UPLOAD_SUBMISSION: "Upload files to create or update a submission.",
    Capability.GENERATE_AI_TEST_CASES: "Use AI to generate new test scripts based on solution or starter code.",
    Capability.MANAGE_DATASETS: "Upload, edit, or delete datasets mounted during code execution.",
    Capability.DOWNLOAD_ASSIGNMENT_FILES: "Download instructor-provided assignment files as a ZIP.",
    # Submission
    Capability.VIEW_SUBMISSION: "View the submission files.",
    Capability.VIEW_FEEDBACK: "View grades, comments, and rubric applications on a submission.",
    Capability.GRADE_SUBMISSION: "Add or edit grades, apply rubric comments, and finalize submissions.",
    Capability.COMMENT_ON_SUBMISSION: "Create, edit, or delete inline code comments on a submission.",
    Capability.FINALIZE_SUBMISSION: "Mark a submission as fully graded and ready for release.",
    Capability.UNFINALIZE_SUBMISSION: "Revert a finalized submission back to in-progress for further grading.",
    Capability.VIEW_STUDENT_IDENTITY: "See the real names and emails of students on a submission (bypasses anonymous grading).",
    Capability.REQUEST_REGRADE: "Submit a regrade request on a finalized submission.",
    Capability.MANAGE_REGRADES: "Review, approve, or reject regrade requests.",
    Capability.RUN_AUTOGRADER: "Execute autograder test cases against a submission.",
    Capability.VIEW_TEST_RESULTS: "View autograder test results on a submission.",
    Capability.RUN_CODE: "Execute submission code in the sandboxed environment.",
    Capability.GENERATE_AI_COMMENTS: "Trigger AI-powered comment generation on a submission.",
    Capability.MANAGE_PARTNERS: "Create or remove partner links on a submission.",
    Capability.NOTIFY_STUDENTS_FEEDBACK: "Send an email notification to students that their feedback is ready.",
    Capability.VIEW_AI_ASSISTANCE: "View AI-generated grading summaries and suggested comments.",
    Capability.TRIGGER_AI_ASSISTANCE: "Manually trigger or regenerate AI grading assistance on a submission.",
    Capability.MANAGE_GLOBAL_TEMPLATES: "Promote pinned comments to global templates visible to all graders.",
    Capability.VIEW_SUBMISSION_HISTORY: "View the full history of views and actions on a submission.",
    Capability.PROVIDE_COMMENT_FEEDBACK: "Rate rubric comments with thumbs up or down feedback.",
    # Platform
    Capability.CREATE_COURSE: "Create new courses within an organization.",
    Capability.MANAGE_ORGANIZATION: "Edit organization settings, SSO configuration, and default course options.",
    Capability.IMPERSONATE_USER: "Log in as another user for debugging and support.",
    Capability.ACCESS_ADMIN_DASHBOARD: "Access the platform-wide administration dashboard.",
}


# ---------------------------------------------------------------------------
# Course-scoped key restrictions
# ---------------------------------------------------------------------------

# Capabilities that are unconditionally disabled when the request is
# authenticated with a course-scoped API key.  These are platform-level
# or cross-course operations that make no sense for a key tied to a
# single course.
COURSE_SCOPED_BLOCKED_CAPABILITIES: set[Capability] = {
    Capability.CREATE_COURSE,
    Capability.MANAGE_ORGANIZATION,
    Capability.ACCESS_ADMIN_DASHBOARD,
    Capability.MANAGE_COURSE_API_KEYS,
}


# ---------------------------------------------------------------------------
# Compute functions
# ---------------------------------------------------------------------------

def compute_course_capabilities(user, course, *, is_course_scoped: bool = False, _rc: RoleCache | None = None) -> dict[Capability, bool]:
    """Return a dict of ``{capability_key: bool}`` for the given user/course.

    Only includes course-level capabilities.  Does **not** hit any
    assignment or submission-specific state.

    Pass a ``RoleCache`` via ``_rc`` to avoid redundant DB queries when
    this function is called as part of a hierarchical chain.
    """
    rc = _rc or RoleCache(user)
    admin = rc.is_course_admin(course)
    staff = rc.is_course_staff(course)
    member = rc.is_course_member(course)
    grader = rc.is_grader(course)
    rubric_editor = rc.is_rubric_editor(course)
    super_grader = rc.is_super_grader(course)
    archived = course.archived
    org_staff = hasattr(user, 'profile') and user.profile.isOrgStaff

    caps = {
        Capability.VIEW_COURSE: member,
        Capability.EDIT_COURSE_SETTINGS: (admin or org_staff) and not archived,
        Capability.MANAGE_ROSTER: admin and not archived,
        Capability.VIEW_ROSTER: staff or admin,
        Capability.MANAGE_SECTIONS: admin and not archived,
        Capability.VIEW_ANALYTICS: admin,
        Capability.CONFIGURE_AI: admin,
        Capability.VIEW_AI_USAGE: admin,
        Capability.CREATE_ASSIGNMENT: admin and not archived,
        Capability.CLAIM_SUBMISSIONS: (grader or admin) and course.activateQueue and not archived,
        Capability.EDIT_RUBRIC: (admin or rubric_editor or (grader and course.allowGradersToEditRubric)) and not archived,
        Capability.MANAGE_REGRADES: admin or super_grader,
        Capability.VIEW_AUDIT_LOG: admin,
        Capability.CHANGE_INVITE_CODE: admin,
        Capability.MANAGE_COURSE_API_KEYS: admin,
    }

    if is_course_scoped:
        for cap in COURSE_SCOPED_BLOCKED_CAPABILITIES:
            if cap in caps:
                caps[cap] = False

    return caps


def compute_assignment_capabilities(user, assignment, *, _rc: RoleCache | None = None) -> dict[Capability, bool]:
    """Return a dict of ``{capability_key: bool}`` for the given user/assignment.

    Includes course-level capabilities plus assignment-specific ones.
    """
    rc = _rc or RoleCache(user)
    course = assignment.course
    caps = compute_course_capabilities(user, course, _rc=rc)

    admin = rc.is_course_admin(course)
    staff = rc.is_course_staff(course)
    student = rc.is_student(course)
    grader = rc.is_grader(course)
    rubric_editor = rc.is_rubric_editor(course)
    archived = course.archived

    # Rubric editing: admin always; rubric editors if explicitly flagged;
    # all graders if the course-level setting is on.
    can_edit_rubric = admin or rubric_editor or (grader and course.allowGradersToEditRubric)

    # Students can view the rubric only after feedback is released or live mode is on
    student_can_see_rubric = (
        student and (assignment.feedbackReleased or assignment.liveFeedbackMode)
    )

    super_grader = rc.is_super_grader(course)

    caps.update({
        Capability.EDIT_ASSIGNMENT: admin and not archived,
        Capability.COPY_ASSIGNMENT: admin,
        Capability.VIEW_ASSIGNMENT: staff or (student and assignment.isVisible),
        Capability.EDIT_RUBRIC: can_edit_rubric and not archived,
        Capability.VIEW_RUBRIC: staff or student_can_see_rubric,
        Capability.RELEASE_GRADES: admin,
        Capability.MANAGE_EXTENSIONS: admin,
        Capability.VIEW_QUEUE: staff,
        Capability.MANAGE_TEST_CASES: admin,
        Capability.VIEW_ASSIGNMENT_STATISTICS: admin,
        Capability.UPLOAD_SUBMISSION: (student and getattr(assignment, 'allowStudentUpload', False) and not archived) or (admin and not archived),
        Capability.GENERATE_AI_TEST_CASES: (admin or super_grader) and not archived,
        Capability.MANAGE_DATASETS: admin and not archived,
        Capability.DOWNLOAD_ASSIGNMENT_FILES: staff or (student and assignment.isVisible),
        Capability.MANAGE_GLOBAL_TEMPLATES: admin or super_grader,
    })
    return caps


def compute_submission_capabilities(user, submission, *, _rc: RoleCache | None = None) -> dict[Capability, bool]:
    """Return a dict of ``{capability_key: bool}`` for the given user/submission.

    Includes course + assignment capabilities plus submission-specific ones.
    """
    rc = _rc or RoleCache(user)
    assignment = submission.assignment
    course = assignment.course
    caps = compute_assignment_capabilities(user, assignment, _rc=rc)

    admin = rc.is_course_admin(course)
    staff_of_sub = rc.is_staff_of_sub(submission)
    student_of_sub = rc.is_student_of_sub(submission)
    archived = course.archived
    super_grader = rc.is_super_grader(course)
    feedback_available = assignment.feedbackReleased or assignment.liveFeedbackMode

    _student = rc.is_student(course)

    caps.update({
        Capability.VIEW_SUBMISSION: staff_of_sub or student_of_sub,
        Capability.VIEW_FEEDBACK: staff_of_sub or (student_of_sub and feedback_available),
        Capability.GRADE_SUBMISSION: staff_of_sub and not archived,
        Capability.COMMENT_ON_SUBMISSION: staff_of_sub and not archived,
        Capability.FINALIZE_SUBMISSION: staff_of_sub and not archived,
        Capability.UNFINALIZE_SUBMISSION: (admin or (staff_of_sub and not course.noUnfinalize)) and not archived,
        Capability.VIEW_STUDENT_IDENTITY: rc.can_view_unanonymized_submissions(course),
        Capability.REQUEST_REGRADE: student_of_sub and bool(getattr(assignment, 'allowRegradeRequests', False)),
        Capability.MANAGE_REGRADES: admin or super_grader,
        Capability.RUN_AUTOGRADER: staff_of_sub,
        Capability.VIEW_TEST_RESULTS: staff_of_sub or (student_of_sub and feedback_available),
        Capability.RUN_CODE: staff_of_sub or student_of_sub,
        Capability.GENERATE_AI_COMMENTS: staff_of_sub and not getattr(course, 'ai_disabled', False) and not getattr(course, 'ai_comments_disabled', False),
        Capability.MANAGE_PARTNERS: student_of_sub and bool(getattr(assignment, 'allowStudentUploadWithPartners', False)) and not archived,
        Capability.NOTIFY_STUDENTS_FEEDBACK: staff_of_sub,
        Capability.VIEW_AI_ASSISTANCE: staff_of_sub and not getattr(course, 'ai_disabled', False),
        Capability.TRIGGER_AI_ASSISTANCE: staff_of_sub and not getattr(course, 'ai_disabled', False),
        Capability.MANAGE_GLOBAL_TEMPLATES: admin or super_grader,
        Capability.VIEW_SUBMISSION_HISTORY: admin or super_grader or staff_of_sub,
        Capability.PROVIDE_COMMENT_FEEDBACK: student_of_sub and bool(getattr(assignment, 'commentFeedback', True)),
    })
    return caps


def compute_platform_capabilities(user) -> dict[Capability, bool]:
    """Return platform-level capabilities (not scoped to a course)."""
    superuser = user.is_superuser
    try:
        profile = user.profile
        org_staff = profile.isOrgStaff
        can_create = profile.canCreateCourses
    except Exception:
        org_staff = False
        can_create = False

    return {
        Capability.CREATE_COURSE: superuser or can_create,
        Capability.MANAGE_ORGANIZATION: superuser or org_staff,
        Capability.IMPERSONATE_USER: superuser,
        Capability.ACCESS_ADMIN_DASHBOARD: superuser,
    }


# ---------------------------------------------------------------------------
# Enforcement helpers
# ---------------------------------------------------------------------------

def _resolve_capabilities(user, obj) -> dict[Capability, bool]:
    """Compute capabilities for a user on the given object (Course, Assignment, or Submission)."""
    # Import models locally to avoid circular imports
    from core.models import Course, Assignment, Submission

    if isinstance(obj, Course):
        return compute_course_capabilities(user, obj)
    elif isinstance(obj, Assignment):
        return compute_assignment_capabilities(user, obj)
    elif isinstance(obj, Submission):
        return compute_submission_capabilities(user, obj)
    else:
        raise TypeError(f"check_capability: unsupported object type {type(obj).__name__}")


def check_capability(user, capability: Union[str, Capability], obj) -> bool:
    """Check if a user has a specific capability on an object.

    Returns ``True`` if the capability is granted, ``False`` otherwise.
    Accepts either a ``Capability`` enum member or its string value.
    """
    key = capability.value if isinstance(capability, Capability) else capability
    caps = _resolve_capabilities(user, obj)
    return caps.get(key, False)


def require_capability(user, capability: Union[str, Capability], obj) -> None:
    """Raise ``PermissionDenied`` if the user lacks the given capability.

    Use this in view action methods to replace inline ``isCourseAdmin()``
    and similar checks::

        require_capability(request.user, 'manage_roster', course)
    """
    key = capability.value if isinstance(capability, Capability) else capability
    if not check_capability(user, key, obj):
        raise PermissionDenied(f"You do not have the '{key}' capability on this resource.")
