# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.contrib import admin
from log.models import Event, TrackedAutograderRun
import json
from django.utils.html import format_html
from django.utils.safestring import mark_safe
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "category",
        "user",
        "description",
        "courseID",
        "created",
        
    )
    list_filter = ("category", "courseID", "user")
    search_fields = ("description", "meta")
    def meta_formatted(self, obj):
        """
        Display the meta field as formatted JSON with enhanced styling.
        """
        if obj.meta:
            try:
                meta_json = json.loads(obj.meta)
                
                def get_value_elements(value, indent_level=0):
                    indent = "&nbsp;" * (indent_level * 4)
                    try:
                        if isinstance(value, dict):
                            items = []
                            for k, v in value.items():
                                nested = get_value_elements(v, indent_level + 1)
                                items.append(f'{indent}<span style="color: #2196F3; font-weight: 600;">{k}:</span> {nested}')
                            return "<br>".join(items)
                        elif isinstance(value, list):
                            items = []
                            for i, item in enumerate(value):
                                nested = get_value_elements(item, indent_level + 1)
                                items.append(f'{indent}<span style="color: #9E9E9E;">•</span> {nested}')
                            return "<br>".join(items)
                        elif isinstance(value, str):
                            parsed = json.loads(value)
                            return get_value_elements(parsed, indent_level)
                        else:
                            return f'<span style="color: #4CAF50;">{value}</span>'
                    except (json.JSONDecodeError, TypeError):
                        return f'<span style="color: #424242;">{value}</span>'
                
                sub_elements = []
                for key, value in meta_json.items():
                    value_elements = get_value_elements(value, 1)
                    sub_elements.append(
                        f'<div style="margin-bottom: 12px;">'
                        f'<span style="color: #1976D2; font-weight: 700; font-size: 14px;">{key}</span><br>'
                        f'{value_elements}</div>'
                    )
                
                formatted_json = "".join(sub_elements)
                
                return mark_safe(
                    f'<div style="background: linear-gradient(to bottom, #f8f9fa 0%, #ffffff 100%); '
                    f'padding: 16px; border-radius: 8px; border: 1px solid #e0e0e0; '
                    f'font-family: \'Segoe UI\', Roboto, sans-serif; font-size: 13px; '
                    f'max-width: 900px; overflow-x: auto; box-shadow: 0 2px 4px rgba(0,0,0,0.05); '
                    f'line-height: 1.6;">{formatted_json}</div>'
                )
            except json.JSONDecodeError:
                return mark_safe(
                    f'<div style="background-color: #ffebee; padding: 16px; border-radius: 8px; '
                    f'border-left: 4px solid #f44336; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">'
                    f'<strong style="color: #d32f2f; font-size: 14px;">⚠ Invalid JSON</strong><br>'
                    f'<pre style="margin-top: 8px; font-size: 12px; color: #424242;">{obj.meta}</pre></div>'
                )
        return mark_safe('<em style="color: #9e9e9e; font-style: italic;">No metadata available</em>')
    
    meta_formatted.short_description = "Meta (formatted)"

    readonly_fields = ("meta_formatted",)



admin.site.register(Event, EventAdmin)


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
