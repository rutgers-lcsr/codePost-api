from django.db import migrations
from django.db.models import F


def backfill_graded_at(apps, schema_editor):
    # gradedAt is new; for rows graded before it existed, `modified` is a close proxy —
    # apply_manual_grade saves the row immediately after stamping gradedBy.
    QuizResponse = apps.get_model('core', 'QuizResponse')
    QuizResponse.objects.filter(gradedBy__isnull=False, gradedAt__isnull=True).update(
        gradedAt=F('modified'))


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0147_course_graderscangradequizzes_quizresponse_gradedat_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_graded_at, migrations.RunPython.noop),
    ]
