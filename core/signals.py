"""
Core application signals.

Handles automatic submission execution when submissions are created.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from core.models import Submission
import time

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Submission)
def auto_execute_submission(sender, instance, created, **kwargs):
    """
    Automatically execute submission when it's created or updated.
    
    This signal fires after a Submission is saved. If auto-execution is enabled,
    it queues the RunSubmission Celery task to execute all code files in the submission.
    This happens both when submissions are created AND when they are updated.
    
    Configuration:
        AUTOGRADER_AUTO_EXECUTE (bool): Enable/disable auto-execution (default: False)
    
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

from core.models import AssignmentFile
from django.db.models.signals import post_delete

@receiver(post_save, sender=AssignmentFile)
@receiver(post_delete, sender=AssignmentFile)
def auto_detect_on_file_change(sender, instance, **kwargs):
    """
    Trigger auto-detection when assignment files change.
    """
    try:
        from autograder.services.autodetector import Autodetector
        # AssignmentFile has 'assignment' FK
        assignment = instance.assignment
        logger.info(f"AssignmentFile changed for {assignment.id}. Triggering auto-detection.")
        Autodetector.detect_and_update(assignment=assignment)
    except Exception as e:
        logger.error(f"Failed to run auto-detection for assignment file change: {e}")
