from django.contrib import admin
from core.models import *

# Custom admin models


class OrganizationAdmin(admin.ModelAdmin):
    search_fields = (
        "name",
        "shortname",
    )


admin.site.register(Organization, OrganizationAdmin)


class ProfileAdmin(admin.ModelAdmin):
    search_fields = ("user__email",)

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ("api_token",)
        return self.readonly_fields


admin.site.register(Profile, ProfileAdmin)


class CourseAdmin(admin.ModelAdmin):
    search_fields = (
        "name",
        "period",
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + (
                "students",
                "graders",
                "courseAdmins",
                "superGraders",
                "inactive_students",
                "inactive_graders",
                "inactive_courseAdmins",
            )
        return self.readonly_fields


admin.site.register(Course, CourseAdmin)


class AssignmentAdmin(admin.ModelAdmin):
    search_fields = ("name", "course__name", "course__period")

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ("course",)
        return self.readonly_fields


admin.site.register(Assignment, AssignmentAdmin)


class CommentAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ("file", "author", "rubricComment")
        return self.readonly_fields


admin.site.register(Comment, CommentAdmin)


class CommentTagAdmin(admin.ModelAdmin):
    search_fields = ("label",)


admin.site.register(CommentTag, CommentTagAdmin)


class SectionAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ("course", "leaders", "students")
        return self.readonly_fields


admin.site.register(Section, SectionAdmin)


class FileAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ("submission",)
        return self.readonly_fields


admin.site.register(File, FileAdmin)


class RubricCategoryAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ("assignment",)
        return self.readonly_fields


class SubmissionTestAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ("submission",)
        return self.readonly_fields


admin.site.register(RubricCategory, RubricCategoryAdmin)
# Models registered under default admin interface
admin.site.register(RubricComment)
admin.site.register(Submission)
admin.site.register(SubmissionHistory)
admin.site.register(FileTemplate)
admin.site.register(SubmissionTest, SubmissionTestAdmin)
admin.site.register(TestCase)


class EnvironmentAdmin(admin.ModelAdmin):
    list_filter = ("language",)

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ("assignment",)
        return self.readonly_fields

    # Django admin seems to be saving carraige returns for compile text
    # Replace if admin console saves
    def save_model(self, request, obj, form, change):
        obj.compileText = obj.compileText.replace("\r", "")
        super().save_model(request, obj, form, change)


admin.site.register(Environment, EnvironmentAdmin)
admin.site.register(SourceFile)
admin.site.register(HelperFile)
admin.site.register(SolutionFile)
