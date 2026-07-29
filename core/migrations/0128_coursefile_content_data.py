# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import uuid

from django.db import migrations


def forwards(apps, schema_editor):
    """Move each CourseFile's data/token/isPublic onto its own CourseFileContent row.

    Idempotent (filters content__isnull=True) and chunked — rows can hold up to 25MB of
    base64 data. Tokens are copied 1:1 from a column that was already unique, so the
    unique constraint on CourseFileContent.token cannot collide.
    """
    CourseFile = apps.get_model("core", "CourseFile")
    CourseFileContent = apps.get_model("core", "CourseFileContent")
    File = apps.get_model("core", "File")
    for cf in CourseFile.objects.filter(content__isnull=True).iterator(chunk_size=20):
        content = CourseFileContent.objects.create(
            data=cf.data, token=cf.token, isPublic=cf.isPublic,
            created=cf.created, modified=cf.modified)
        CourseFile.objects.filter(pk=cf.pk).update(content=content)
        # MTI: the CourseFile pk is the File row's pk. The row's data/hash are dead now.
        File.objects.filter(pk=cf.pk).update(data="", hash="")


def backwards(apps, schema_editor):
    """Dev-only convenience: copy content back onto the rows. The lowest-id row per
    content keeps the token/isPublic; any other sharer gets a fresh token (its public
    URL dies — sharing cannot be represented in the old schema). Not for production."""
    CourseFile = apps.get_model("core", "CourseFile")
    File = apps.get_model("core", "File")
    seen_content_ids = set()
    for cf in CourseFile.objects.filter(content__isnull=False).order_by("pk").iterator(chunk_size=20):
        first = cf.content_id not in seen_content_ids
        seen_content_ids.add(cf.content_id)
        CourseFile.objects.filter(pk=cf.pk).update(
            token=cf.content.token if first else uuid.uuid4(),
            isPublic=cf.content.isPublic if first else False,
        )
        File.objects.filter(pk=cf.pk).update(data=cf.content.data)


class Migration(migrations.Migration):
    """Step 2: backfill. atomic=False so a MySQL run avoids one giant transaction and
    can be safely retried (forwards is idempotent)."""

    atomic = False

    dependencies = [
        ("core", "0127_coursefilecontent"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
