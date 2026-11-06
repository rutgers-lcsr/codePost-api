# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.db import migrations


def force_roster_flag_for_org_staff(apps, schema_editor):
    # Profile.save() now forces canModifyRosters on for org staff; bring existing rows in line.
    Profile = apps.get_model('core', 'Profile')
    Profile.objects.filter(isOrgStaff=True, canModifyRosters=False).update(canModifyRosters=True)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0156_profile_isdisabled'),
    ]

    operations = [
        migrations.RunPython(force_roster_flag_for_org_staff, migrations.RunPython.noop),
    ]
