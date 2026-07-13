# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Core application signals.

Handles automatic submission execution when submissions are created.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from core.models import QuizGeneratedSection, Submission
import time

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Submission)
def auto_execute_submission(sender, instance, created, **kwargs):
    """
    Automatically execute submission when it's created or updated.
    
    This signal fires after a Submission is saved. If auto-execution is enabled,
    it queues the RunSubmission Celery task to execute all code files in the submission
    and (if the assignment has runTestsOnSubmit enabled) run the test suite.
    This happens both when submissions are created AND when they are updated.
    
    Configuration:
        AUTOGRADER_AUTO_EXECUTE (bool): Enable/disable auto-execution (default: False)
    
    The per-assignment ``runFilesOnSubmit`` and ``runTestsOnSubmit`` flags are
    checked inside the RunSubmission task to decide whether to execute files
    and/or run tests.  If both are disabled, the task is not queued at all.
    
    Args:
        sender: The Submission model class
        instance: The Submission instance that was saved
        created: Boolean indicating if this is a new instance
        **kwargs: Additional signal arguments
    """

    # check if files updated
    update = kwargs.get('update_fields', None)
    if not (update and 'dateUploaded' in update) and not created:
        logger.debug(
            f"Submission {instance.id} updated without file changes. "
            "Skipping auto-execution."
        )
        return


    # Check if auto-execution is enabled
    auto_execute = getattr(settings, 'AUTOGRADER_AUTO_EXECUTE', False)
    if not auto_execute:
        logger.debug(
            f"Auto-execution disabled. Skipping submission {instance.id}. "
            "Set AUTOGRADER_AUTO_EXECUTE=True to enable."
        )
        return

    # Check per-assignment flags — skip if both are disabled
    run_files = getattr(instance.assignment, 'runFilesOnSubmit', True)
    run_tests = getattr(instance.assignment, 'runTestsOnSubmit', True)
    if not run_files and not run_tests:
        logger.debug(
            f"Both runFilesOnSubmit and runTestsOnSubmit disabled for "
            f"assignment {instance.assignment.id}. Skipping."
        )
        return
    
    try:
        # Import here to avoid circular imports
        from autograder.run import RunSubmission
        
        if not RunSubmission:
            logger.error("RunSubmission task not found. Cannot auto-execute submission.")
            return

        # Attempt Auto-Detection of Environment
        # We do this before execution so the run uses the correct environment settings.
        try:
            from autograder.services.autodetector import Autodetector
            Autodetector.detect_and_update(instance)
        except Exception as e:
            logger.error(f"Auto-detection failed for submission {instance.id}: {e}")
        
        # wait 1 second
        # Submission files are not immediately available after upload
        time.sleep(1)
        
        # Queue the execution task
        task = RunSubmission.delay(instance.id) # type: ignore
        
        action = "created" if created else "updated"
        logger.info(
            f"Queued execution for submission {instance.id} ({action}) "
            f"(task_id: {task.id})"
        )
        
    except ImportError as e:
        logger.error(
            f"Failed to import RunSubmission task: {e}. "
            "Make sure autograder app is properly configured."
        )
    except Exception as e:
        logger.error(
            f"Failed to queue execution for submission {instance.id}: {e}",
            exc_info=True
        )


@receiver(post_save, sender=Submission)
def auto_generate_personalized_quiz(sender, instance, created, **kwargs):
    """Queue per-student quiz question generation when a submission is created or its
    files are uploaded, for attached quizzes that have generated sections.

    Feature/config checks (AI configured, personalized_quiz_generation enabled,
    regenerate-unless-approved) live in the task, matching the quiz-suggestion pattern.
    """
    # Same guard as auto_execute_submission: only on creation or a real file upload.
    update = kwargs.get('update_fields', None)
    if not (update and 'dateUploaded' in update) and not created:
        return

    try:
        if not instance.assignment.quizzes.filter(generatedSections__isnull=False).exists():
            return
        # Import here to avoid circular imports.
        from core.tasks import generate_personalized_quiz_sets
        # Submission files are not immediately available after the row save (the existing
        # signal sleeps 1s for the same reason) — give the upload a moment to land.
        generate_personalized_quiz_sets.apply_async(args=[instance.id], countdown=10)
        logger.info(f"Queued personalized quiz generation for submission {instance.id}")
    except Exception as e:
        logger.error(
            f"Failed to queue personalized quiz generation for submission {instance.id}: {e}",
            exc_info=True
        )


@receiver(post_save, sender=QuizGeneratedSection)
def backfill_generated_sets_on_section_created(sender, instance, created, **kwargs):
    """Backfill question generation when an AI section is created AFTER students already
    submitted — the submission signal above only covers submissions made while a section
    exists, so without this, earlier submitters would sit on "being prepared" forever.
    Also refreshes existing non-approved sets, which the new section makes incomplete."""
    if not created:
        return
    if instance.quiz.assignment_id is None:
        return
    try:
        from core.tasks import backfill_personalized_quiz_sets
        backfill_personalized_quiz_sets.delay(instance.quiz_id)
        logger.info(f"Queued personalized quiz backfill for quiz {instance.quiz_id} "
                    f"(section {instance.id} created)")
    except Exception as e:
        logger.error(
            f"Failed to queue personalized quiz backfill for quiz {instance.quiz_id}: {e}",
            exc_info=True
        )


from core.models import AssignmentFile
from django.db.models.signals import post_delete

@receiver(post_save, sender=AssignmentFile)
@receiver(post_delete, sender=AssignmentFile)
def auto_detect_on_file_change(sender, instance, **kwargs):
    """
    Trigger auto-detection when assignment files change.
    """
    try:
        from autograder.run import AutoDetectEnvironment
        # Use async task with delay to debounce and handle cascade deletions gracefully
        # If assignment is deleted, the task will fail (benignly) when it runs
        AutoDetectEnvironment.apply_async(args=[instance.assignment_id], countdown=2)
    except Exception as e:
        logger.error(f"Failed to queue auto-detection for assignment file change: {e}")


from core.models import Environment

@receiver(post_delete, sender=Environment)
def cleanup_environment_images(sender, instance, **kwargs):
    """
    Trigger cleanup of Docker images when Environment is deleted.
    """
    try:
        from autograder.run import DeleteEnvironmentImages
        DeleteEnvironmentImages.delay(instance.id)
        logger.info(f"Queued image cleanup for deleted environment {instance.id}")
    except Exception as e:
        logger.error(f"Failed to queue image cleanup for environment {instance.id}: {e}")


@receiver(post_save, sender='core.PromptFeedback')
def check_auto_improve_threshold(sender, instance, created, **kwargs):
    """Dispatch threshold-based auto-improvement when new feedback is created.

    The actual threshold check happens inside the Celery task to avoid
    adding latency to the feedback save path.
    """
    if not created:
        return
    if instance.is_custom_context:
        return

    try:
        from core.tasks import auto_improve_prompt_threshold
        auto_improve_prompt_threshold.delay(instance.prompt_type)
    except Exception as e:
        logger.debug(f"Failed to dispatch auto-improve threshold check: {e}")
