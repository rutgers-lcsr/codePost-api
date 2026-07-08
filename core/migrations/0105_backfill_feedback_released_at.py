# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""Backfill Assignment.feedbackReleasedAt for assignments already released before the field
existed (added in 0100). Assignment.save() only stamps it on a False→True transition, so
pre-existing released assignments keep it NULL, which makes a quiz's 'feedback_released'
close never fire. Use `modified` as the best available proxy for the release time.
"""
from django.db import migrations, models


def backfill_feedback_released_at(apps, schema_editor):
    Assignment = apps.get_model("core", "Assignment")
    Assignment.objects.filter(
        feedbackReleased=True, feedbackReleasedAt__isnull=True
    ).update(feedbackReleasedAt=models.F("modified"))


def unset_feedback_released_at(apps, schema_editor):
    # Reverse: clear values where feedback is released (symmetric with the forward filter;
    # can't distinguish backfilled from genuinely-stamped after the fact).
    Assignment = apps.get_model("core", "Assignment")
    Assignment.objects.filter(feedbackReleased=True).update(feedbackReleasedAt=None)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0104_quiz_snapshot_scoring"),
    ]

    operations = [
        migrations.RunPython(backfill_feedback_released_at, unset_feedback_released_at),
    ]
