# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.db import migrations, models


class Migration(migrations.Migration):
    """Per-course student-facing metadata: an optional description and a studentVisible
    toggle gating the student course file directory. Row-level (not on the shared
    CourseFileContent) — each course decides what its own students see."""

    dependencies = [
        ("core", "0129_coursefile_finalize_content"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursefile",
            name="description",
            field=models.TextField(
                blank=True,
                help_text="Optional description shown to students.",
            ),
        ),
        migrations.AddField(
            model_name="coursefile",
            name="studentVisible",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "If True, students in the course can see and download this file in "
                    "their course file directory. Staff always see all files."
                ),
            ),
        ),
    ]
