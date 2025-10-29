from django.contrib import admin
from django.db.models import Count, Q
from django.utils.html import format_html
from django.urls import reverse, path
from django.utils.safestring import mark_safe
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from typing import Any, Optional

from core.models import (
    Assignment,
    AssignmentFile,
    AssignmentDataSet,
    CachedExecutionResult,
    Comment,
    CommentTag,
    Course,
    CourseFile,
    Environment,
    File,
    FileTemplate,
    HelperFile,
    OneTimeToken,
    Organization,
    Profile,
    RubricCategory,
    RubricComment,
    Section,
    SolutionFile,
    SourceFile,
    Submission,
    SubmissionFile,
    SubmissionHistory,
    SubmissionTest,
    TestCase,
    TestCategory,
)

# ============================================================================
# Site Configuration
# ============================================================================

admin.site.site_header = "codePost Administration"
admin.site.site_title = "codePost Admin"
admin.site.index_title = "Welcome to codePost Administration"


# ============================================================================
# Custom Admin Classes
# ============================================================================


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("shortname", "name", "profile_count", "course_count", "created", "modified")
    search_fields = ("name", "shortname")
    list_filter = ("created", "modified")
    ordering = ("name",)
    readonly_fields = ("created", "modified")
    
    def profile_count(self, obj: Organization) -> int:
        """Number of profiles in this organization"""
        return obj.profiles.count()
    profile_count.short_description = "Profiles"
    
    def course_count(self, obj: Organization) -> int:
        """Number of courses in this organization"""
        return obj.courses.count()
    course_count.short_description = "Courses"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related().prefetch_related("profiles", "courses")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user_email", "organization", "can_create_courses", "can_modify_rosters", 
                    "pending_validation", "is_password_set", "created")
    search_fields = ("user__email", "user__username", "organization__name")
    list_filter = ("canCreateCourses", "canModifyRosters", "pendingValidation", 
                   "isPasswordSet", "organization", "created")
    readonly_fields = ("api_token", "created", "modified")
    autocomplete_fields = ["user", "organization"]
    
    fieldsets = (
        ("User Information", {
            "fields": ("user", "organization", "api_token")
        }),
        ("Permissions", {
            "fields": ("canCreateCourses", "canModifyRosters", "pendingValidation")
        }),
        ("Settings", {
            "fields": ("showProductTips", "isPasswordSet", "stripeCustomerId")
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def user_email(self, obj: Profile) -> str:
        """Display user email"""
        return obj.user.email
    user_email.short_description = "Email"
    user_email.admin_order_field = "user__email"
    
    def can_create_courses(self, obj: Profile) -> bool:
        return obj.canCreateCourses
    can_create_courses.short_description = "Can Create Courses"
    can_create_courses.boolean = True
    
    def can_modify_rosters(self, obj: Profile) -> bool:
        return obj.canModifyRosters
    can_modify_rosters.short_description = "Can Modify Rosters"
    can_modify_rosters.boolean = True
    
    def pending_validation(self, obj: Profile) -> bool:
        return obj.pendingValidation
    pending_validation.short_description = "Pending"
    pending_validation.boolean = True
    
    def is_password_set(self, obj: Profile) -> bool:
        return obj.isPasswordSet
    is_password_set.short_description = "Password Set"
    is_password_set.boolean = True
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("user", "organization")


@admin.register(OneTimeToken)
class OneTimeTokenAdmin(admin.ModelAdmin):
    list_display = ("token_preview", "user_email", "is_valid_status", "used", "expires_at", "created")
    search_fields = ("user__email", "user__username", "token")
    list_filter = ("used", "created", "expires_at")
    readonly_fields = ("token", "user", "expires_at", "created", "modified", "copy_token_button")
    
    fieldsets = (
        ("Token Information", {
            "fields": ("user", "token", "copy_token_button")
        }),
        ("Status", {
            "fields": ("used", "expires_at")
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    actions = ["generate_new_tokens"]
    
    def has_add_permission(self, request: Any) -> bool:
        """Disable add form - tokens should be generated via the action"""
        return False
    
    def changelist_view(self, request: Any, extra_context: Any = None) -> Any:
        """Add custom button to changelist"""
        extra_context = extra_context or {}
        extra_context['generate_token_url'] = reverse('admin:generate_token')
        return super().changelist_view(request, extra_context)
    
    def get_urls(self):
        """Add custom URL for generating token"""
        urls = super().get_urls()
        custom_urls = [
            path('generate-token/', self.admin_site.admin_view(self.generate_token_view), name='generate_token'),
        ]
        return custom_urls + urls
    
    def generate_token_view(self, request: Any) -> HttpResponseRedirect:
        """View to generate a new token for the current user"""
        from django.contrib import messages
        
        token = OneTimeToken.objects.create(user=request.user)
        messages.success(request, format_html(
            'New token generated: <strong style="font-family: monospace; background: #f0f0f0; padding: 2px 6px;">{}</strong>',
            token.token
        ))
        return redirect('admin:core_onetimetoken_changelist')
    
    def token_preview(self, obj: OneTimeToken) -> str:
        """Display first and last 8 characters of token"""
        token_str = str(obj.token)
        if len(token_str) > 20:
            return f"{token_str[:8]}...{token_str[-8:]}"
        return token_str
    token_preview.short_description = "Token"
    
    def user_email(self, obj: OneTimeToken) -> str:
        """Display user email"""
        return obj.user.email
    user_email.short_description = "User"
    user_email.admin_order_field = "user__email"
    
    def is_valid_status(self, obj: OneTimeToken) -> bool:
        """Check if token is still valid"""
        return obj.is_valid()
    is_valid_status.short_description = "Valid"
    is_valid_status.boolean = True
    
    def copy_token_button(self, obj: OneTimeToken) -> str:
        """Display a copyable token field"""
        if obj.token:
            return format_html(
                '<div style="font-family: monospace; background: #f5f5f5; padding: 10px; border: 1px solid #ddd; border-radius: 4px;">'
                '<div style="margin-bottom: 5px;"><strong>Token:</strong></div>'
                '<input type="text" value="{}" readonly style="width: 100%; padding: 5px; font-family: monospace;" '
                'onclick="this.select(); document.execCommand(\'copy\'); alert(\'Token copied to clipboard!\');" />'
                '<div style="margin-top: 5px; font-size: 11px; color: #666;">Click to select and copy</div>'
                '</div>',
                obj.token
            )
        return "-"
    copy_token_button.short_description = "Copy Token"
    
    def generate_new_tokens(self, request: Any, queryset: Any) -> None:
        """Generate a new token for the current user (admin)"""
        # Create a new token for the logged-in admin user
        token = OneTimeToken.objects.create(user=request.user)
        self.message_user(request, f"New token generated for {request.user.email}: {token.token}")
    generate_new_tokens.short_description = "Generate token for me (current admin user)"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("user")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "period", "organization", "student_count", "grader_count", 
                    "admin_count", "assignment_count", "is_archived", "created")
    search_fields = ("name", "period", "organization__name")
    list_filter = ("archived", "organization", "created", "modified")
    readonly_fields = ("created", "modified")
    autocomplete_fields = ["organization"]
    filter_horizontal = ("students", "graders", "courseAdmins", "superGraders",
                        "inactive_students", "inactive_graders", "inactive_courseAdmins")
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("id", "name", "period", "organization", "archived")
        }),
        ("Settings", {
            "fields": ("timezone", "sendReleasedSubmissionsToBack", "showStudentsStatistics",
                      "emailNewUsers", "anonymousGradingDefault", "allowGradersToEditRubric",
                      "minComments", "noUnfinalize", "activateQueue")
        }),
        ("Student Management", {
            "fields": ("rosterMap", "emailWhitelist", "lateDayCreditsAllowable", 
                      "studentCaptions", "useStudentCaptions", "inviteCode", "inviteCodeEnabled"),
            "classes": ("collapse",)
        }),
        ("Active Members", {
            "fields": ("students", "graders", "courseAdmins", "superGraders"),
            "classes": ("collapse",)
        }),
        ("Inactive Members", {
            "fields": ("inactive_students", "inactive_graders", "inactive_courseAdmins"),
            "classes": ("collapse",)
        }),
        ("Notifications", {
            "fields": ("enableStudentFeedbackNotifications",),
            "classes": ("collapse",)
        }),
        ("Payments & Waivers", {
            "fields": ("manual_payments", "waiver_requested"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    actions = ["archive_courses", "unarchive_courses"]
    
    def student_count(self, obj: Course) -> int:
        return obj.students.count()
    student_count.short_description = "Students"
    
    def grader_count(self, obj: Course) -> int:
        return obj.graders.count()
    grader_count.short_description = "Graders"
    
    def admin_count(self, obj: Course) -> int:
        return obj.courseAdmins.count()
    admin_count.short_description = "Admins"
    
    def assignment_count(self, obj: Course) -> int:
        return obj.assignments.count()
    assignment_count.short_description = "Assignments"
    
    def is_archived(self, obj: Course) -> bool:
        return obj.archived
    is_archived.short_description = "Archived"
    is_archived.boolean = True
    
    def archive_courses(self, request: Any, queryset: Any) -> None:
        """Archive selected courses"""
        updated = queryset.update(archived=True)
        self.message_user(request, f"{updated} course(s) archived.")
    archive_courses.short_description = "Archive selected courses"
    
    def unarchive_courses(self, request: Any, queryset: Any) -> None:
        """Unarchive selected courses"""
        updated = queryset.update(archived=False)
        self.message_user(request, f"{updated} course(s) unarchived.")
    unarchive_courses.short_description = "Unarchive selected courses"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("organization").prefetch_related(
            "students", "graders", "courseAdmins", "assignments"
        )


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "points", "is_visible", "is_released", 
                    "submission_count", "mean_grade", "created")
    search_fields = ("name", "course__name", "course__period")
    list_filter = ("isVisible", "isReleased", "allowStudentUpload", "anonymousGrading",
                   "created", "modified")
    readonly_fields = ("course", "mean", "median", "created", "modified")
    autocomplete_fields = ["course"]
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "course", "points", "sortKey", "explanation")
        }),
        ("Visibility", {
            "fields": ("isVisible", "isReleased", "hideGrades", "anonymousGrading")
        }),
        ("Student Upload Settings", {
            "fields": ("allowStudentUpload", "allowStudentUploadWithPartners", 
                      "uploadDueDate"),
            "classes": ("collapse",)
        }),
        ("Grading Settings", {
            "fields": ("additiveGrading", "liveFeedbackMode", "commentFeedback"),
            "classes": ("collapse",)
        }),
        ("Statistics", {
            "fields": ("mean", "median"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    actions = ["release_assignments", "hide_assignments", "enable_student_upload"]
    
    def submission_count(self, obj: Assignment) -> int:
        return obj.submissions.count()
    submission_count.short_description = "Submissions"
    
    def mean_grade(self, obj: Assignment) -> Optional[str]:
        if obj.mean:
            return f"{obj.mean:.2f}"
        return "-"
    mean_grade.short_description = "Mean"
    mean_grade.admin_order_field = "mean"
    
    def is_visible(self, obj: Assignment) -> bool:
        return obj.isVisible
    is_visible.short_description = "Visible"
    is_visible.boolean = True
    
    def is_released(self, obj: Assignment) -> bool:
        return obj.isReleased
    is_released.short_description = "Released"
    is_released.boolean = True
    
    def release_assignments(self, request: Any, queryset: Any) -> None:
        """Release selected assignments"""
        updated = queryset.update(isReleased=True, isVisible=True)
        self.message_user(request, f"{updated} assignment(s) released.")
    release_assignments.short_description = "Release selected assignments"
    
    def hide_assignments(self, request: Any, queryset: Any) -> None:
        """Hide selected assignments"""
        updated = queryset.update(isVisible=False)
        self.message_user(request, f"{updated} assignment(s) hidden.")
    hide_assignments.short_description = "Hide selected assignments"
    
    def enable_student_upload(self, request: Any, queryset: Any) -> None:
        """Enable student upload for selected assignments"""
        updated = queryset.update(allowStudentUpload=True)
        self.message_user(request, f"Student upload enabled for {updated} assignment(s).")
    enable_student_upload.short_description = "Enable student upload"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("course").prefetch_related("submissions")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "leader_count", "student_count", "created")
    search_fields = ("name", "course__name")
    list_filter = ("course", "created")
    readonly_fields = ("created", "modified")
    autocomplete_fields = ["course"]
    filter_horizontal = ("leaders", "students")
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "course")
        }),
        ("Members", {
            "fields": ("leaders", "students")
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def leader_count(self, obj: Section) -> int:
        return obj.leaders.count()
    leader_count.short_description = "Leaders"
    
    def student_count(self, obj: Section) -> int:
        return obj.students.count()
    student_count.short_description = "Students"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("course").prefetch_related("leaders", "students")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "assignment", "students_list", "grader", "grade", 
                    "is_finalized", "has_question", "date_uploaded")
    search_fields = ("id", "assignment__name", "students__email", "grader__email")
    list_filter = ("isFinalized", "questionIsOpen", "questionIsRegrade", 
                   "assignment__course", "created")
    readonly_fields = ("assignment", "dateEdited", "dateUploaded", "created", "modified")
    autocomplete_fields = ["assignment", "grader", "questionResponder"]
    filter_horizontal = ("students",)
    
    fieldsets = (
        ("Assignment Information", {
            "fields": ("assignment", "students", "grader")
        }),
        ("Grading", {
            "fields": ("isFinalized", "grade", "gradeFrozen", "queueOrderKey")
        }),
        ("Late Submission", {
            "fields": ("lateDayCreditsUsed",),
            "classes": ("collapse",)
        }),
        ("Question/Regrade", {
            "fields": ("questionIsOpen", "questionIsRegrade", "questionText", 
                      "questionResponse", "questionResponder", "questionDate", "responseDate"),
            "classes": ("collapse",)
        }),
        ("Testing", {
            "fields": ("testRunsCompleted",),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("dateUploaded", "dateEdited", "created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    actions = ["finalize_submissions", "unfinalize_submissions"]
    
    def students_list(self, obj: Submission) -> str:
        emails = [s.email for s in obj.students.all()[:3]]
        count = obj.students.count()
        if count > 3:
            return ", ".join(emails) + f" (+{count - 3} more)"
        return ", ".join(emails)
    students_list.short_description = "Students"
    
    def is_finalized(self, obj: Submission) -> bool:
        return obj.isFinalized
    is_finalized.short_description = "Finalized"
    is_finalized.boolean = True
    
    def has_question(self, obj: Submission) -> bool:
        return obj.questionIsOpen
    has_question.short_description = "Question"
    has_question.boolean = True
    
    def date_uploaded(self, obj: Submission) -> Any:
        return obj.dateUploaded
    date_uploaded.short_description = "Uploaded"
    date_uploaded.admin_order_field = "dateUploaded"
    
    def finalize_submissions(self, request: Any, queryset: Any) -> None:
        """Finalize selected submissions"""
        updated = queryset.update(isFinalized=True)
        self.message_user(request, f"{updated} submission(s) finalized.")
    finalize_submissions.short_description = "Finalize selected submissions"
    
    def unfinalize_submissions(self, request: Any, queryset: Any) -> None:
        """Unfinalize selected submissions"""
        updated = queryset.update(isFinalized=False)
        self.message_user(request, f"{updated} submission(s) unfinalized.")
    unfinalize_submissions.short_description = "Unfinalize selected submissions"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("assignment", "grader").prefetch_related("students")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "author", "point_delta", "text_preview", "created")
    search_fields = ("text", "author__email", "file__submission__id")
    list_filter = ("created", "rubricComment")
    readonly_fields = ("file", "author", "rubricComment", "created", "modified")
    autocomplete_fields = ["file", "author", "rubricComment"]
    filter_horizontal = ("tags",)
    
    fieldsets = (
        ("Location", {
            "fields": ("file", "startLine", "endLine", "startChar", "endChar")
        }),
        ("Content", {
            "fields": ("text", "pointDelta", "rubricComment", "author")
        }),
        ("Appearance", {
            "fields": ("color", "tags"),
            "classes": ("collapse",)
        }),
        ("Feedback", {
            "fields": ("feedback",),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def text_preview(self, obj: Comment) -> str:
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text
    text_preview.short_description = "Text"
    
    def point_delta(self, obj: Comment) -> Optional[str]:
        if obj.pointDelta is not None:
            return f"{obj.pointDelta:+.2f}"
        return "-"
    point_delta.short_description = "Points"
    point_delta.admin_order_field = "pointDelta"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("file", "author", "rubricComment")


@admin.register(CommentTag)
class CommentTagAdmin(admin.ModelAdmin):
    list_display = ("label", "comment_count", "created")
    search_fields = ("label",)
    list_filter = ("created",)
    readonly_fields = ("created", "modified")
    
    def comment_count(self, obj: CommentTag) -> int:
        return obj.tag_comments.count()
    comment_count.short_description = "Comments"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.prefetch_related("tag_comments")


@admin.register(RubricCategory)
class RubricCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "assignment", "point_limit", "sort_key", "at_most_once", "created")
    search_fields = ("name", "assignment__name")
    list_filter = ("atMostOnce", "assignment__course", "created")
    readonly_fields = ("assignment", "created", "modified")
    autocomplete_fields = ["assignment"]
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("assignment", "name", "helpText")
        }),
        ("Settings", {
            "fields": ("pointLimit", "sortKey", "atMostOnce")
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def point_limit(self, obj: RubricCategory) -> str:
        return str(obj.pointLimit) if obj.pointLimit is not None else "-"
    point_limit.short_description = "Point Limit"
    point_limit.admin_order_field = "pointLimit"
    
    def sort_key(self, obj: RubricCategory) -> int:
        return obj.sortKey
    sort_key.short_description = "Sort"
    sort_key.admin_order_field = "sortKey"
    
    def at_most_once(self, obj: RubricCategory) -> bool:
        return obj.atMostOnce
    at_most_once.short_description = "At Most Once"
    at_most_once.boolean = True
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("assignment")


@admin.register(RubricComment)
class RubricCommentAdmin(admin.ModelAdmin):
    list_display = ("name_or_text", "category", "point_delta", "sort_key", "created")
    search_fields = ("text", "name", "category__name")
    list_filter = ("category__assignment", "created")
    readonly_fields = ("created", "modified")
    autocomplete_fields = ["category"]
    
    fieldsets = (
        ("Content", {
            "fields": ("name", "text", "explanation", "pointDelta")
        }),
        ("Template Settings", {
            "fields": ("instructionText", "templateTextOn"),
            "classes": ("collapse",)
        }),
        ("Organization", {
            "fields": ("category", "sortKey")
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def name_or_text(self, obj: RubricComment) -> str:
        if obj.name:
            return obj.name
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text
    name_or_text.short_description = "Name/Text"
    
    def point_delta(self, obj: RubricComment) -> str:
        return f"{obj.pointDelta:+.2f}"
    point_delta.short_description = "Points"
    point_delta.admin_order_field = "pointDelta"
    
    def sort_key(self, obj: RubricComment) -> int:
        return obj.sortKey
    sort_key.short_description = "Sort"
    sort_key.admin_order_field = "sortKey"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("category", "category__assignment")


@admin.register(SubmissionHistory)
class SubmissionHistoryAdmin(admin.ModelAdmin):
    list_display = ("submission", "student", "has_viewed", "date_viewed", "created")
    search_fields = ("submission__id", "student__email")
    list_filter = ("hasViewed", "created")
    readonly_fields = ("submission", "student", "dateViewed", "created", "modified")
    autocomplete_fields = ["submission", "student"]
    
    def has_viewed(self, obj: SubmissionHistory) -> bool:
        return obj.hasViewed
    has_viewed.short_description = "Viewed"
    has_viewed.boolean = True
    
    def date_viewed(self, obj: SubmissionHistory) -> Optional[Any]:
        return obj.dateViewed
    date_viewed.short_description = "Viewed At"
    date_viewed.admin_order_field = "dateViewed"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("submission", "student")


@admin.register(SubmissionFile)
class SubmissionFileAdmin(admin.ModelAdmin):
    list_display = ("id", "file_name", "submission", "students_list", "created")
    search_fields = ("name", "submission__id", "submission__students__email")
    list_filter = ("hiddenBeforePublish", "created")
    readonly_fields = ("submission", "created", "modified")
    autocomplete_fields = ["submission"]
    
    fieldsets = (
        ("File Information", {
            "fields": ("name", "extension", "path")
        }),
        ("Submission", {
            "fields": ("submission", "hiddenBeforePublish")
        }),
        ("Content", {
            "fields": ("data",),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def file_name(self, obj: SubmissionFile) -> str:
        return obj.name
    file_name.short_description = "File Name"
    file_name.admin_order_field = "name"
    
    def students_list(self, obj: SubmissionFile) -> str:
        if obj.submission:
            emails = [s.email for s in obj.submission.students.all()[:2]]
            count = obj.submission.students.count()
            if count > 2:
                return ", ".join(emails) + f" (+{count - 2} more)"
            return ", ".join(emails)
        return "-"
    students_list.short_description = "Students"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("submission").prefetch_related("submission__students")


@admin.register(AssignmentFile)
class AssignmentFileAdmin(admin.ModelAdmin):
    list_display = ("id", "file_name", "assignment", "required", "created")
    search_fields = ("name", "assignment__name")
    list_filter = ("required", "created")
    readonly_fields = ("assignment", "created", "modified")
    autocomplete_fields = ["assignment"]
    
    fieldsets = (
        ("File Information", {
            "fields": ("name", "extension", "path")
        }),
        ("Assignment", {
            "fields": ("assignment", "required", "description")
        }),
        ("Content", {
            "fields": ("data",),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def file_name(self, obj: AssignmentFile) -> str:
        return obj.name
    file_name.short_description = "File Name"
    file_name.admin_order_field = "name"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("assignment")

@admin.register(CachedExecutionResult)
class CachedExecutionResultAdmin(admin.ModelAdmin):
    list_display = ("id", "file_name", "executed_by_email", "executed_at", "execution_time", "file_type", "created")
    search_fields = ("file__name", "executed_by__email", "file_content_hash")
    list_filter = ("executed_at", "created")
    readonly_fields = ("file", "executed_by", "executed_at", "file_content_hash", 
                        "execution_time_seconds", "created", "modified")
    autocomplete_fields = ["file", "executed_by"]
    
    fieldsets = (
        ("File Information", {
            "fields": ("file", "file_content_hash")
        }),
        ("Execution Details", {
            "fields": ("executed_by", "executed_at", "execution_time_seconds")
        }),
        ("Output Data", {
            "fields": ("output_data",),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def file_name(self, obj: CachedExecutionResult) -> str:
        return obj.file.name if obj.file else "-"
    file_name.short_description = "File Name"
    file_name.admin_order_field = "file__name"
    
    def executed_by_email(self, obj: CachedExecutionResult) -> str:
        return obj.executed_by.email if obj.executed_by else "-"
    executed_by_email.short_description = "Executed By"
    executed_by_email.admin_order_field = "executed_by__email"
    
    def execution_time(self, obj: CachedExecutionResult) -> str:
        if obj.execution_time_seconds is not None:
            return f"{obj.execution_time_seconds:.2f}s"
        return "-"
    execution_time.short_description = "Execution Time"
    execution_time.admin_order_field = "execution_time_seconds"
    
    def file_type(self, obj: CachedExecutionResult) -> str:
        return obj.file.__class__.__name__ if obj.file else "-"
    file_type.short_description = "File Type"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("file", "executed_by")
    
@admin.register(AssignmentDataSet)
class AssignmentDataSetAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "assignment", "created")
    search_fields = ("name", "assignment__name")
    list_filter = ("created",)
    readonly_fields = ("assignment", "created", "modified")
    autocomplete_fields = ["assignment"]
    
    fieldsets = (
        ("Data Set Information", {
            "fields": ("name", "assignment", "description")
        }),
        ("Content", {
            "fields": ("mount_path", ),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("assignment")
    
@admin.register(CourseFile)
class CourseFileAdmin(admin.ModelAdmin):
    list_display = ("id", "file_name", "course", "created")
    search_fields = ("name", "course__name")
    list_filter = ("course", "created")
    readonly_fields = ("course", "created", "modified")
    autocomplete_fields = ["course"]
    
    def file_name(self, obj: CourseFile) -> str:
        return obj.name
    file_name.short_description = "File Name"
    file_name.admin_order_field = "name"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("course")


@admin.register(TestCategory)
class TestCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "assignment", "test_case_count", "created")
    search_fields = ("name", "assignment__name")
    list_filter = ("assignment__course", "created")
    readonly_fields = ("assignment", "created", "modified")
    autocomplete_fields = ["assignment"]
    
    def test_case_count(self, obj: TestCategory) -> int:
        return obj.testCases.count()
    test_case_count.short_description = "Test Cases"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("assignment").prefetch_related("testCases")


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ("description", "testCategory", "type", "points_pass", "points_fail", 
                    "sort_key", "created")
    search_fields = ("description", "testCategory__name")
    list_filter = ("type", "testCategory__assignment", "created")
    readonly_fields = ("testCategory", "created", "modified")
    autocomplete_fields = ["testCategory"]
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("testCategory", "description", "type", "sortKey")
        }),
        ("Points", {
            "fields": ("pointsPass", "pointsFail")
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def points_pass(self, obj: TestCase) -> str:
        return f"{obj.pointsPass:+.2f}"
    points_pass.short_description = "Pass Points"
    points_pass.admin_order_field = "pointsPass"
    
    def points_fail(self, obj: TestCase) -> str:
        return f"{obj.pointsFail:+.2f}"
    points_fail.short_description = "Fail Points"
    points_fail.admin_order_field = "pointsFail"
    
    def sort_key(self, obj: TestCase) -> int:
        return obj.sortKey
    sort_key.short_description = "Sort"
    sort_key.admin_order_field = "sortKey"
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("testCategory", "testCategory__assignment")


@admin.register(SubmissionTest)
class SubmissionTestAdmin(admin.ModelAdmin):
    list_display = ("submission", "testCase", "passed", "is_error", "created")
    search_fields = ("submission__id", "testCase__description")
    list_filter = ("passed", "isError", "created")
    readonly_fields = ("submission", "testCase", "created", "modified")
    autocomplete_fields = ["submission", "testCase"]
    
    fieldsets = (
        ("Test Information", {
            "fields": ("submission", "testCase", "passed", "isError")
        }),
        ("Results", {
            "fields": ("logs",),
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def is_error(self, obj: SubmissionTest) -> bool:
        return obj.isError
    is_error.short_description = "Error"
    is_error.boolean = True
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("submission", "testCase")


@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    list_display = ("assignment", "language", "build_type", "created")
    search_fields = ("assignment__name",)
    list_filter = ("language", "buildType", "created")
    readonly_fields = ("assignment", "created", "modified")
    autocomplete_fields = ["assignment"]
    
    fieldsets = (
        ("Assignment", {
            "fields": ("assignment",)
        }),
        ("Configuration", {
            "fields": ("language", "buildType", "dockerfile", "compileText")
        }),
        ("Docker Settings", {
            "fields": ("dockerRunInstructions",),
            "classes": ("collapse",)
        }),
        ("Testing Settings", {
            "fields": ("allowNetworkAccess", "maxStudentTestRuns", "maxExposedFailedTests", 
                      "exposeDumpLogs", "parseTestsOnSave"),
            "classes": ("collapse",)
        }),
        ("Build", {
            "fields": ("buildID",),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created", "modified"),
            "classes": ("collapse",)
        }),
    )
    
    def build_type(self, obj: Environment) -> str:
        return obj.buildType
    build_type.short_description = "Build Type"
    build_type.admin_order_field = "buildType"
    
    # Django admin seems to be saving carriage returns for compile text
    # Replace if admin console saves
    def save_model(self, request: Any, obj: Environment, form: Any, change: bool) -> None:
        obj.compileText = obj.compileText.replace("\r", "")
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("assignment")


@admin.register(SolutionFile)
class SolutionFileAdmin(admin.ModelAdmin):
    list_display = ("name", "environment", "created")
    search_fields = ("name", "environment__assignment__name")
    list_filter = ("created",)
    readonly_fields = ("environment", "created", "modified")
    autocomplete_fields = ["environment"]
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("environment", "environment__assignment")


@admin.register(HelperFile)
class HelperFileAdmin(admin.ModelAdmin):
    list_display = ("name", "environment", "created")
    search_fields = ("name", "environment__assignment__name")
    list_filter = ("created",)
    readonly_fields = ("environment", "created", "modified")
    autocomplete_fields = ["environment"]
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("environment", "environment__assignment")


@admin.register(SourceFile)
class SourceFileAdmin(admin.ModelAdmin):
    list_display = ("name", "environment", "created")
    search_fields = ("name", "environment__assignment__name")
    list_filter = ("created",)
    readonly_fields = ("environment", "created", "modified")
    autocomplete_fields = ["environment"]
    
    def get_queryset(self, request: Any) -> Any:
        qs = super().get_queryset(request)
        return qs.select_related("environment", "environment__assignment")


# Register File model with search_fields for autocomplete
@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "extension",)
    search_fields = ("name", "extension")
    list_filter = ("extension",)
    readonly_fields = ("created", "modified")





# Deprecated model, but keep in admin for data access
admin.site.register(FileTemplate)



