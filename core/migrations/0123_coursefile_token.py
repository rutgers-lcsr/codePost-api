# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import uuid

from django.db import migrations, models


def populate_tokens(apps, schema_editor):
    """Give every existing CourseFile a unique token before the unique constraint lands."""
    CourseFile = apps.get_model("core", "CourseFile")
    for cf in CourseFile.objects.filter(token__isnull=True):
        cf.token = uuid.uuid4()
        cf.save(update_fields=["token"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0122_coursefile_ispublic"),
    ]

    operations = [
        # Step 1: add as a nullable column with NO default so existing rows get NULL
        # (a callable default would populate every row with the same value → not unique).
        migrations.AddField(
            model_name="coursefile",
            name="token",
            field=models.UUIDField(
                null=True,
                editable=False,
                db_index=True,
                help_text="Unguessable token used in the public download URL.",
            ),
        ),
        # Step 2: backfill a unique token per existing row.
        migrations.RunPython(populate_tokens, migrations.RunPython.noop),
        # Step 3: enforce the final shape (default + unique, non-null).
        migrations.AlterField(
            model_name="coursefile",
            name="token",
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                editable=False,
                db_index=True,
                help_text="Unguessable token used in the public download URL.",
            ),
        ),
    ]
