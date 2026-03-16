# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.db import migrations


AUDIT_CATEGORIES = [
    "Become User",
    "Generate One-Time Token",
    "One-Time Token Generated",
    "Admin New Request Approved",
    "Admin New Request Denied",
    "Admin Change Organization Request",
    "Admin Already Exists",
    "Admin New Request Error",
    "New Org Admin Request",
    "Existing Org Admin Request",
    "CIP Activation",
    "Codepost Registration Error",
]


def backfill_event_type(apps, schema_editor):
    Event = apps.get_model("log", "Event")
    Event.objects.filter(category__in=AUDIT_CATEGORIES).update(type="audit")


def reverse_backfill(apps, schema_editor):
    Event = apps.get_model("log", "Event")
    Event.objects.filter(type="audit").update(type="activity")


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0004_add_type_to_event"),
    ]

    operations = [
        migrations.RunPython(backfill_event_type, reverse_backfill),
    ]
