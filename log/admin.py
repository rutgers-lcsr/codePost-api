# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.contrib import admin
from log.models import Event, TrackedAutograderRun
import json
from django.utils.html import escape
from django.utils.safestring import mark_safe
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "category",
        "user",
        "description",
        "has_diagnostics",
        "has_screenshot",
        "courseID",
        "created",
    )
    list_filter = ("category", "courseID", "user")
    search_fields = ("description", "meta")

    fieldsets = (
        ("Event Info", {
            "fields": ("category", "user", "description", "courseID", "created", "updated"),
        }),
        ("Diagnostic Details", {
            "fields": ("browser_context_display", "console_logs_display", "screenshot_preview", "meta_formatted"),
            "classes": ("wide",),
        }),
    )
    readonly_fields = (
        "created", "updated", "meta_formatted",
        "browser_context_display", "console_logs_display", "screenshot_preview",
        "has_diagnostics", "has_screenshot",
    )

    def _parse_meta(self, obj):
        """Parse the meta JSON field, returning the dict or None."""
        if not obj.meta:
            return None
        try:
            return json.loads(obj.meta)
        except (json.JSONDecodeError, TypeError):
            return None

    def _parse_error_detail(self, obj):
        """Parse the errorDetail string inside meta, returning the dict or None."""
        meta = self._parse_meta(obj)
        if not meta:
            return None
        error_detail = meta.get("errorDetail", "")
        if not error_detail:
            return None
        if isinstance(error_detail, dict):
            return error_detail
        try:
            return json.loads(error_detail)
        except (json.JSONDecodeError, TypeError):
            return None

    def has_diagnostics(self, obj):
        detail = self._parse_error_detail(obj)
        return bool(detail and detail.get("type") == "user-report")
    has_diagnostics.boolean = True
    has_diagnostics.short_description = "Diagnostics"

    def has_screenshot(self, obj):
        meta = self._parse_meta(obj)
        return bool(meta and meta.get("screenshot"))
    has_screenshot.boolean = True
    has_screenshot.short_description = "Screenshot"

    def browser_context_display(self, obj):
        """Show browser context (user agent, platform, viewport, performance, etc.)."""
        detail = self._parse_error_detail(obj)
        if not detail:
            return mark_safe('<em style="color: #9e9e9e;">No browser context available</em>')

        context_keys = [
            ("userAgent", "User Agent"),
            ("platform", "Platform"),
            ("language", "Language"),
            ("cookiesEnabled", "Cookies Enabled"),
            ("viewport", "Viewport"),
            ("connection", "Connection"),
            ("performance", "Performance"),
            ("memory", "Memory"),
            ("storage", "Storage"),
            ("timestamp", "Timestamp"),
            ("url", "URL"),
            ("category", "Category"),
            ("description", "User Description"),
        ]
        rows = []
        for key, label in context_keys:
            value = detail.get(key)
            if value is None:
                continue
            if isinstance(value, dict):
                value_str = json.dumps(value, indent=2)
                escaped = escape(value_str)
                rows.append(
                    f'<tr><td style="font-weight:600;vertical-align:top;padding:4px 12px 4px 0;color:#1976D2;">'
                    f'{escape(label)}</td>'
                    f'<td style="padding:4px 0;"><pre style="margin:0;font-size:12px;white-space:pre-wrap;">'
                    f'{escaped}</pre></td></tr>'
                )
            else:
                rows.append(
                    f'<tr><td style="font-weight:600;vertical-align:top;padding:4px 12px 4px 0;color:#1976D2;">'
                    f'{escape(label)}</td>'
                    f'<td style="padding:4px 0;">{escape(str(value))}</td></tr>'
                )

        if not rows:
            return mark_safe('<em style="color: #9e9e9e;">No browser context available</em>')

        table = "".join(rows)
        return mark_safe(
            f'<div style="background:#f8f9fa;padding:12px;border-radius:6px;border:1px solid #e0e0e0;'
            f'max-width:900px;font-family:sans-serif;font-size:13px;">'
            f'<table>{table}</table></div>'
        )
    browser_context_display.short_description = "Browser Context"

    def console_logs_display(self, obj):
        """Show recent console logs captured at the time of the report."""
        detail = self._parse_error_detail(obj)
        if not detail:
            return mark_safe('<em style="color: #9e9e9e;">No console logs available</em>')

        logs = detail.get("recentConsoleLogs", [])
        if not logs:
            return mark_safe('<em style="color: #9e9e9e;">No console logs captured</em>')

        level_colors = {"error": "#d32f2f", "warn": "#f57c00", "info": "#1976D2", "log": "#424242"}
        rows = []
        for entry in logs:
            if isinstance(entry, dict):
                level = entry.get("level", "log")
                message = entry.get("message", "")
                timestamp = entry.get("timestamp", "")
            else:
                level = "log"
                message = str(entry)
                timestamp = ""
            color = level_colors.get(level, "#424242")
            ts_display = f'<span style="color:#9E9E9E;font-size:11px;">{escape(str(timestamp))}</span> ' if timestamp else ""
            rows.append(
                f'<div style="padding:3px 0;border-bottom:1px solid #eee;">'
                f'{ts_display}'
                f'<span style="color:{color};font-weight:600;">[{escape(level)}]</span> '
                f'<span style="font-family:monospace;font-size:12px;">{escape(str(message))}</span>'
                f'</div>'
            )

        return mark_safe(
            f'<div style="background:#f8f9fa;padding:12px;border-radius:6px;border:1px solid #e0e0e0;'
            f'max-width:900px;max-height:400px;overflow-y:auto;font-family:sans-serif;font-size:13px;">'
            f'<div style="margin-bottom:8px;font-weight:700;color:#424242;">'
            f'{len(logs)} console log(s)</div>'
            f'{"".join(rows)}</div>'
        )
    console_logs_display.short_description = "Console Logs"

    def screenshot_preview(self, obj):
        """Show the screenshot as an inline image if available."""
        meta = self._parse_meta(obj)
        if not meta or not meta.get("screenshot"):
            return mark_safe('<em style="color: #9e9e9e;">No screenshot attached</em>')

        screenshot = meta["screenshot"]
        # The screenshot is a base64 data URL (e.g. data:image/jpeg;base64,...)
        return mark_safe(
            f'<div style="max-width:900px;">'
            f'<img src="{screenshot}" style="max-width:100%;border:1px solid #e0e0e0;border-radius:6px;" />'
            f'</div>'
        )
    screenshot_preview.short_description = "Screenshot"

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
                                items.append(f'{indent}<span style="color: #2196F3; font-weight: 600;">{escape(str(k))}:</span> {nested}')
                            return "<br>".join(items)
                        elif isinstance(value, list):
                            items = []
                            for _, item in enumerate(value):
                                nested = get_value_elements(item, indent_level + 1)
                                items.append(f'{indent}<span style="color: #9E9E9E;">•</span> {nested}')
                            return "<br>".join(items)
                        elif isinstance(value, str):
                            parsed = json.loads(value)
                            return get_value_elements(parsed, indent_level)
                        else:
                            return f'<span style="color: #4CAF50;">{escape(str(value))}</span>'
                    except (json.JSONDecodeError, TypeError):
                        return f'<span style="color: #424242;">{escape(str(value))}</span>'
                
                sub_elements = []
                for key, value in meta_json.items():
                    if key == "screenshot":
                        continue  # Shown separately in screenshot_preview
                    value_elements = get_value_elements(value, 1)
                    sub_elements.append(
                        f'<div style="margin-bottom: 12px;">'
                        f'<span style="color: #1976D2; font-weight: 700; font-size: 14px;">{escape(str(key))}</span><br>'
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
                    f'<pre style="margin-top: 8px; font-size: 12px; color: #424242;">{escape(obj.meta)}</pre></div>'
                )
        return mark_safe('<em style="color: #9e9e9e; font-style: italic;">No metadata available</em>')
    
    meta_formatted.short_description = "Raw Meta (formatted)"


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
