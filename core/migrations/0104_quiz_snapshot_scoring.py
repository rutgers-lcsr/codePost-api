# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
# Hand-written (equivalent to makemigrations output) — see 0105 for the feedbackReleasedAt backfill.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0103_course_quizgraders_quizresponse_gradedby_and_more"),
    ]

    operations = [
        # QuizResponse: fully snapshot the presented question so later edits/deletion of the
        # live question don't alter or destroy in-flight/graded attempts.
        migrations.RemoveField(
            model_name="quizresponse",
            name="selectedChoices",
        ),
        migrations.AddField(
            model_name="quizresponse",
            name="questionSnapshot",
            field=models.JSONField(
                default=dict,
                help_text=(
                    "Immutable copy of the presented question at attempt time: "
                    "{questionId, type, text, description, starterCode, language, generalFeedback, "
                    "choices:[{id, text, isCorrect, feedback, sortKey}]}."
                ),
            ),
        ),
        migrations.AddField(
            model_name="quizresponse",
            name="selectedChoiceKeys",
            field=models.JSONField(
                default=list,
                help_text=(
                    "Selected option id(s) into questionSnapshot.choices, for choice-based questions."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="quizresponse",
            name="question",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="core.question",
                help_text=(
                    "The live question this was drawn from (analytics only; may be deleted). "
                    "Grading/rendering use questionSnapshot, so this is nullable and SET_NULL."
                ),
            ),
        ),
        # QuizAttempt: track the furthest question reached to enforce no-backtracking server-side.
        migrations.AddField(
            model_name="quizattempt",
            name="furthestIndex",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Highest response sortKey the student has reached; enforces sequential "
                    "navigation (oneQuestionAtATime / no-backtracking) server-side."
                ),
            ),
        ),
        # Quiz: how multiple attempts combine into the official score (never mixing denominators).
        migrations.AddField(
            model_name="quiz",
            name="multiAttemptScoreMethod",
            field=models.CharField(
                choices=[
                    ("by_unit", "By passing unit (percentage, or points)"),
                    ("pooled", "Pooled points across attempts"),
                ],
                default="by_unit",
                max_length=8,
                help_text=(
                    "How multiple attempts combine into the official score: 'by_unit' compares/"
                    "averages by the passing unit (percentage, or points); 'pooled' totals points "
                    "earned over total points possible across attempts."
                ),
            ),
        ),
        # CourseAuditEvent: new 'quiz_attempts_reset' event type (choices are Python-level;
        # this AlterField keeps the migration state consistent — no SQL change).
        migrations.AlterField(
            model_name="courseauditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("submission_attempt", "Submission Attempt"),
                    ("submission_failed", "Submission Failed"),
                    ("file_view", "File View"),
                    ("feedback_view", "Feedback View"),
                    ("regrade_request", "Regrade Request"),
                    ("regrade_deleted", "Regrade Deleted"),
                    ("autograder_triggered", "Autograder Triggered"),
                    ("autograder_completed", "Autograder Completed"),
                    ("autograder_failed", "Autograder Failed"),
                    ("late_day_used", "Late Day Used"),
                    ("comment_feedback", "Comment Feedback"),
                    ("quiz_created", "Quiz Created"),
                    ("quiz_updated", "Quiz Updated"),
                    ("quiz_published", "Quiz Published"),
                    ("quiz_unpublished", "Quiz Unpublished"),
                    ("quiz_deleted", "Quiz Deleted"),
                    ("quiz_attempt_started", "Quiz Attempt Started"),
                    ("quiz_attempt_submitted", "Quiz Attempt Submitted"),
                    ("quiz_attempt_autosubmitted", "Quiz Attempt Auto-Submitted"),
                    ("quiz_attempts_reset", "Quiz Attempts Reset"),
                ],
                help_text="The type of event",
                max_length=32,
            ),
        ),
    ]
