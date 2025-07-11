from django.contrib import admin
from log.models import Event, TrackedAutograderRun

admin.site.register(Event)


class TrackedAutograderRunAdmin(admin.ModelAdmin):
    readonly_fields = (
        "started",
        "ended",
        "run_by",
        "submission",
        "assignment",
    )
    list_display = (
        "id",
        "get_organization",
        "assignment",
        "run_by",
        "duration",
        "test_case_set",
        "run_by_role",
    )

    @admin.display(description="Organization")
    def get_organization(self, obj):
        return obj.assignment.course.organization


admin.site.register(TrackedAutograderRun, TrackedAutograderRunAdmin)
