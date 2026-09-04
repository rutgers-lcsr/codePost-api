# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Backfill Assignment.state from the legacy isVisible/isReleased booleans (added in 0139).

The mapping is behavior-preserving for students:
  isVisible=False                                    -> draft      (hidden today)
  isVisible=True, isReleased=False, no student upload -> preview   (see + download, no submit)
  isVisible=True, isReleased=False, student upload    -> published (see + download + submit —
                                                        the documented pre-release-upload flow)
  isReleased=True                                     -> published

Nothing maps to 'visible' (opt-in going forward), 'closed' (derived from the deadline),
or 'archived' (a manual action). publishedAt is backfilled from `modified` as the best
available proxy, same as 0105 did for feedbackReleasedAt.
"""
from django.db import migrations, models


def backfill_state(apps, schema_editor):
    Assignment = apps.get_model("core", "Assignment")
    Assignment.objects.filter(isVisible=False).update(state="draft")
    Assignment.objects.filter(
        isVisible=True, isReleased=False, allowStudentUpload=False
    ).update(state="preview")
    Assignment.objects.filter(
        isVisible=True, isReleased=False, allowStudentUpload=True
    ).update(state="published", publishedAt=models.F("modified"))
    Assignment.objects.filter(isVisible=True, isReleased=True).update(
        state="published", publishedAt=models.F("modified")
    )
    # Oddball rows (isVisible=False, isReleased=True) fell into the draft bucket above:
    # hidden wins — students could not see them, so draft preserves that.


def rederive_booleans(apps, schema_editor):
    # Reverse: re-derive the booleans from state and reset state to its default. Lossy by
    # nature (like 0105's reverse): the pre-release-upload bucket comes back released.
    Assignment = apps.get_model("core", "Assignment")
    Assignment.objects.filter(state__in=("visible", "preview", "published", "closed")).update(
        isVisible=True
    )
    Assignment.objects.filter(state__in=("draft", "archived")).update(isVisible=False)
    Assignment.objects.filter(state__in=("published", "closed")).update(isReleased=True)
    Assignment.objects.exclude(state__in=("published", "closed")).update(isReleased=False)
    Assignment.objects.update(state="draft", publishedAt=None)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0139_assignment_publishat_assignment_publishedat_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_state, rederive_booleans),
    ]
