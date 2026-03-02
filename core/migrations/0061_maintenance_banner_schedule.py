from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0060_add_maintenance_banner"),
    ]

    operations = [
        migrations.AddField(
            model_name="maintenancebanner",
            name="severity",
            field=models.CharField(
                choices=[("info", "Info"), ("warning", "Warning"), ("critical", "Critical")],
                default="info",
                help_text="Visual severity of the banner (affects the icon shown to users).",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="maintenancebanner",
            name="starts_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="If set, the banner will not appear before this UTC time even when active=True.",
            ),
        ),
        migrations.AddField(
            model_name="maintenancebanner",
            name="ends_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="If set, the banner auto-hides after this UTC time.",
            ),
        ),
    ]
