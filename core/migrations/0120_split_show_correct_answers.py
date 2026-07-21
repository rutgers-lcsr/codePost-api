# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.db import migrations, models


def split_forward(apps, schema_editor):
    """Map the old 3-value showCorrectAnswers onto the two new booleans:
      never        -> show=False, seal=False
      after_submit -> show=True,  seal=False
      after_close  -> show=True,  seal=True
    """
    Quiz = apps.get_model('core', 'quiz')
    for quiz in Quiz.objects.all():
        old = quiz.showCorrectAnswers_old
        quiz.showCorrectAnswers = old in ('after_submit', 'after_close')
        quiz.sealResultsUntilClose = old == 'after_close'
        quiz.save(update_fields=['showCorrectAnswers', 'sealResultsUntilClose'])


def split_backward(apps, schema_editor):
    """Collapse the two booleans back to the closest old value (the new hide-answers +
    seal-until-close combo has no exact old equivalent; it maps to 'after_close')."""
    Quiz = apps.get_model('core', 'quiz')
    for quiz in Quiz.objects.all():
        if quiz.sealResultsUntilClose:
            quiz.showCorrectAnswers_old = 'after_close'
        elif quiz.showCorrectAnswers:
            quiz.showCorrectAnswers_old = 'after_submit'
        else:
            quiz.showCorrectAnswers_old = 'never'
        quiz.save(update_fields=['showCorrectAnswers_old'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0119_quiz_allowsubmissionreview'),
    ]

    operations = [
        migrations.RenameField('quiz', 'showCorrectAnswers', 'showCorrectAnswers_old'),
        migrations.AddField(
            model_name='quiz',
            name='showCorrectAnswers',
            field=models.BooleanField(
                default=True,
                help_text=('Whether the correct-answer key is shown when a student reviews a '
                           'submitted attempt. Reveal timing follows sealResultsUntilClose.')),
        ),
        migrations.AddField(
            model_name='quiz',
            name='sealResultsUntilClose',
            field=models.BooleanField(
                default=False,
                help_text=('Hold scores, per-question points, and the answer key until the quiz '
                           'closes for the student. When false, results release as soon as an '
                           'attempt is submitted. Stops students with attempts remaining from '
                           'mining the key.')),
        ),
        migrations.RunPython(split_forward, split_backward),
        migrations.RemoveField('quiz', 'showCorrectAnswers_old'),
    ]
