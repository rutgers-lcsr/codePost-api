# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Step 3: make CourseFile.content required and drop the moved columns.

    FORWARD-ONLY IN PRODUCTION: reversing RemoveField cannot restore unique per-row
    tokens on a populated MySQL table (a callable default assigns one shared value).
    The reverse path is only usable on dev/test SQLite databases via 0128's backwards.
    Deploy note: old application code reads CourseFile.token/isPublic — migrate and
    deploy together.
    """

    dependencies = [
        ("core", "0128_coursefile_content_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="coursefile",
            name="content",
            field=models.ForeignKey(
                help_text="Shared file content/visibility.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="files",
                to="core.coursefilecontent",
            ),
        ),
        migrations.RemoveField(
            model_name="coursefile",
            name="isPublic",
        ),
        migrations.RemoveField(
            model_name="coursefile",
            name="token",
        ),
    ]
