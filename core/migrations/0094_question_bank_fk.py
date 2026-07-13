# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Switch Question.banks (M2M) → Question.bank (FK): a question lives in exactly one bank.

Order matters: add the FK with a throwaway reverse name (so it doesn't clash with the
M2M's related_name='questions'), data-migrate, drop the M2M, then finalize the FK as
non-null with related_name='questions'.
"""
import django.db.models.deletion
from django.db import migrations, models


def forwards(apps, schema_editor):
    Question = apps.get_model("core", "Question")
    QuestionBank = apps.get_model("core", "QuestionBank")
    QuestionChoice = apps.get_model("core", "QuestionChoice")

    for q in list(Question.objects.all()):
        bank_ids = list(q.banks.values_list("id", flat=True))

        if not bank_ids:
            # Bankless (e.g. an AI-accept with no target) → per-course "Unfiled questions".
            unfiled, _ = QuestionBank.objects.get_or_create(
                course_id=q.course_id, name="Unfiled questions", defaults={"source": "manual"}
            )
            Question.objects.filter(pk=q.pk).update(bank_id=unfiled.id)
            continue

        # Original keeps the first bank.
        Question.objects.filter(pk=q.pk).update(bank_id=bank_ids[0])

        # Any extra banks → independent copies (question + its choices).
        if len(bank_ids) > 1:
            choices = list(
                QuestionChoice.objects.filter(question_id=q.pk).values(
                    "text", "isCorrect", "sortKey", "feedback"
                )
            )
            for extra_id in bank_ids[1:]:
                dup = Question.objects.create(
                    course_id=q.course_id,
                    bank_id=extra_id,
                    questionType=q.questionType,
                    text=q.text,
                    description=q.description,
                    points=q.points,
                    generalFeedback=q.generalFeedback,
                    language=q.language,
                    starterCode=q.starterCode,
                    referenceSolution=q.referenceSolution,
                    source=q.source,
                    createdBy_id=q.createdBy_id,
                    metadata=q.metadata,
                )
                for c in choices:
                    QuestionChoice.objects.create(question_id=dup.id, **c)


def backwards(apps, schema_editor):
    # Best-effort: re-populate the M2M from the FK (duplicates created above remain).
    Question = apps.get_model("core", "Question")
    for q in Question.objects.exclude(bank_id=None):
        q.banks.set([q.bank_id])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0093_source_imported"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="bank",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="core.questionbank",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name="question",
            name="banks",
        ),
        migrations.AlterField(
            model_name="question",
            name="bank",
            field=models.ForeignKey(
                help_text="The bank this question belongs to (exactly one).",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="core.questionbank",
            ),
        ),
        migrations.AlterField(
            model_name="question",
            name="course",
            field=models.ForeignKey(
                help_text="The related course_id (mirrors bank.course).",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="core.course",
            ),
        ),
    ]
