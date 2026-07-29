# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """Step 1 of the CourseFile copy-on-write change: create the shared content model
    and link CourseFile to it (nullable for now — 0128 backfills, 0129 finalizes)."""

    dependencies = [
        ("core", "0126_quiz_access_code_and_late_start_events"),
    ]

    operations = [
        migrations.CreateModel(
            name="CourseFileContent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        default=django.utils.timezone.now, editable=False
                    ),
                ),
                ("modified", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "data",
                    models.TextField(
                        default="",
                        help_text="The data in a file. should be utf-8 encoded text.",
                    ),
                ),
                (
                    "isPublic",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "If True, the file is downloadable without authentication "
                            "via its public token URL (courseFiles/raw/<token>/)."
                        ),
                    ),
                ),
                (
                    "token",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unguessable token used in the public download URL.",
                        unique=True,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="coursefile",
            name="content",
            field=models.ForeignKey(
                null=True,
                help_text="Shared file content/visibility.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="files",
                to="core.coursefilecontent",
            ),
        ),
    ]
