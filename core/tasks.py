# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from celery import shared_task
from core.models import Course
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@shared_task
def delete_expired_courses():
    """
    Deletes courses whose expiration_date has passed.
    """
    now = timezone.now()
    expired_courses = Course.objects.filter(expiration_date__lte=now)
    count = expired_courses.count()
    
    if count > 0:
        logger.info(f"Deleting {count} expired courses")
        # Depending on how cascade delete works, this might take a while or fail if there are too many related objects.
        # But for test courses it should be fine.
        expired_courses.delete()
    else:
        logger.info("No expired courses found")


@shared_task
def generate_ai_grading_assistance(submission_id: int):
    """
    Generate AI-suggested comments and submission summary for a submission.
    Called after autograder runs complete, or manually via API.

    Skips if:
    - AI is disabled for the course
    - AI is not configured (no provider/key)
    - The submission no longer exists
    """
    from asgiref.sync import async_to_sync
    from core.models import Submission, SuggestedComment, SubmissionSummary
    from core.services.ai_service import AIService
    import json

    try:
        submission = Submission.objects.select_related(
            'assignment', 'assignment__course', 'assignment__course__organization'
        ).get(id=submission_id)
    except Submission.DoesNotExist:
        logger.warning(f"[AIGrading] Submission {submission_id} not found. Skipping.")
        return

    course = submission.assignment.course
    assignment = submission.assignment
    service = AIService(course, assignment)

    if not service.is_configured or service.is_globally_disabled:
        logger.debug(f"[AIGrading] AI not configured or disabled for course {course.id}. Skipping.")
        return

    suggestions_enabled = service.is_feature_enabled('suggested_comments')
    summary_enabled = service.is_feature_enabled('submission_summary')

    if not suggestions_enabled and not summary_enabled:
        logger.debug(f"[AIGrading] Both suggestions and summary disabled for course {course.id}. Skipping.")
        return

    # --- Detect main file for targeted generation ---
    from core.services.file_detection import detect_main_file
    main_file = detect_main_file(submission)

    # --- Generate suggested comments ---
    if not suggestions_enabled:
        logger.debug(f"[AIGrading] Suggested comments disabled for course {course.id}.")
    else:
      try:
        # Clear existing pending suggestions to prevent duplicates on re-trigger
        SuggestedComment.objects.filter(submission=submission, status='pending').delete()

        if main_file:
            # Focus on the detected main file
            results = async_to_sync(service.generate_file_suggestions)(submission, main_file)
        else:
            # Fallback: generate for all files
            results = async_to_sync(service.generate_suggested_comments)(submission)
        for result in results:
            if result.success and result.text:
                suggestions = json.loads(result.text)
                # When targeting a specific file, only save suggestions for that file.
                # When generating for all files, accept any valid file ID.
                if main_file:
                    valid_file_ids = {main_file.id}
                else:
                    valid_file_ids = set(
                        submission.files.values_list('id', flat=True)
                    )
                # Identify notebook files so we can convert 1-based cell numbers
                # (from the AI prompt) to 0-based cell indices (used by the frontend).
                notebook_file_ids = set(
                    submission.files.filter(name__endswith='.ipynb').values_list('id', flat=True)
                )
                created_count = 0
                for s in suggestions:
                    file_id = s.get('file_id')
                    if file_id not in valid_file_ids:
                        continue
                    # For notebooks, convert 1-based cell numbers to 0-based indices
                    start_line = s.get('start_line', 0)
                    end_line = s.get('end_line', 0)
                    if file_id in notebook_file_ids:
                        start_line = max(0, start_line - 1)
                        end_line = max(0, end_line - 1)
                    SuggestedComment.objects.create(
                        submission=submission,
                        file_id=file_id,
                        text=s.get('text', ''),
                        startLine=start_line,
                        endLine=end_line,
                        startChar=s.get('start_char', 0),
                        endChar=s.get('end_char', 0),
                        rubricComment_id=s.get('rubric_comment_id'),
                        pointDelta=s.get('point_delta'),
                        generationMetadata={
                            'provider': service.provider,
                            'model': service.model,
                            'input_tokens': result.input_tokens,
                            'output_tokens': result.output_tokens,
                        },
                    )
                    created_count += 1
                logger.info(f"[AIGrading] Created {created_count} suggested comments for submission {submission_id}")

            service.record_usage(result, user=submission.grader or submission.students.first(), request_type='suggested_comments')

      except Exception as e:
        logger.error(f"[AIGrading] Failed to generate suggested comments for submission {submission_id}: {e}", exc_info=True)

    # --- Generate submission summary ---
    if summary_enabled:
      try:
        result = async_to_sync(service.generate_submission_summary)(submission, target_file=main_file)
        if result.success and result.text:
            SubmissionSummary.objects.update_or_create(
                submission=submission,
                defaults={
                    'text': result.text,
                    'generationMetadata': {
                        'provider': service.provider,
                        'model': service.model,
                        'input_tokens': result.input_tokens,
                        'output_tokens': result.output_tokens,
                    },
                },
            )
            logger.info(f"[AIGrading] Created/updated summary for submission {submission_id}")

        service.record_usage(result, user=submission.grader or submission.students.first(), request_type='submission_summary')

      except Exception as e:
        logger.error(f"[AIGrading] Failed to generate summary for submission {submission_id}: {e}", exc_info=True)

    # --- Auto-generate assignment description if empty and unlocked ---
    if (
        service.is_feature_enabled('assignment_description')
        and not assignment.ai_description
        and not assignment.ai_description_locked
    ):
        # Only auto-generate if we have at least 1 finalized submission to learn from
        finalized_count = assignment.submissions.filter(isFinalized=True).count()
        if finalized_count >= 1 or submission.isFinalized:
            # Re-fetch to guard against concurrent tasks that already generated a description
            from core.models import Assignment as AssignmentModel
            fresh = AssignmentModel.objects.filter(
                id=assignment.id, ai_description='', ai_description_locked=False,
            ).exists()
            if not fresh:
                logger.debug(f"[AIGrading] Description already generated for assignment {assignment.id}, skipping.")
            else:
              try:
                result = async_to_sync(service.generate_assignment_description)(assignment)
                if result.success and result.text:
                    # Re-fetch to avoid race conditions
                    from core.models import Assignment
                    Assignment.objects.filter(
                        id=assignment.id,
                        ai_description='',
                        ai_description_locked=False,
                    ).update(ai_description=result.text)
                    logger.info(f"[AIGrading] Auto-generated description for assignment {assignment.id}")

                service.record_usage(result, user=submission.grader or submission.students.first(), request_type='assignment_description')

              except Exception as e:
                logger.error(f"[AIGrading] Failed to generate assignment description: {e}", exc_info=True)


@shared_task
def auto_improve_prompts_scheduled():
    """Periodic task: auto-improve all prompt types that have enough new feedback.

    Only runs when ``PromptLabSettings.auto_improve_enabled`` and
    ``schedule_enabled`` are both True.
    """
    from core.models import PromptLabSettings, SystemPromptVariant
    from core.services.prompt_improvement import auto_improve_prompt

    settings = PromptLabSettings.load()
    if not settings.auto_improve_enabled or not settings.schedule_enabled:
        logger.info("[AutoImprove] Scheduled run skipped — disabled in settings.")
        return

    prompt_types = [c[0] for c in SystemPromptVariant.PROMPT_TYPE_CHOICES]
    for pt in prompt_types:
        try:
            variant = auto_improve_prompt(
                pt,
                min_feedback=settings.min_feedback,
                triggered_by='schedule',
            )
            if variant:
                logger.info(f"[AutoImprove] Scheduled: created variant {variant.id} for {pt}")
        except Exception:
            logger.exception(f"[AutoImprove] Scheduled run failed for {pt}")


@shared_task
def auto_improve_prompt_threshold(prompt_type: str):
    """Threshold-triggered task: called by the PromptFeedback post_save signal.

    Only runs when ``PromptLabSettings.auto_improve_enabled`` and
    ``threshold_enabled`` are both True, and the new-feedback count since
    the last auto-generated variant exceeds ``feedback_threshold``.
    """
    from core.models import PromptLabSettings, SystemPromptVariant, PromptFeedback
    from core.services.prompt_improvement import auto_improve_prompt

    settings = PromptLabSettings.load()
    if not settings.auto_improve_enabled or not settings.threshold_enabled:
        return

    # Count new default-pool feedback since the last auto-generated variant
    last_auto = SystemPromptVariant.objects.filter(
        prompt_type=prompt_type,
        metadata__auto_generated=True,
    ).order_by('-created').first()

    feedback_qs = PromptFeedback.objects.filter(
        prompt_type=prompt_type,
        is_custom_context=False,
    )
    if last_auto:
        feedback_qs = feedback_qs.filter(created__gt=last_auto.created)

    new_count = feedback_qs.count()
    if new_count < settings.feedback_threshold:
        return

    try:
        variant = auto_improve_prompt(
            prompt_type,
            min_feedback=settings.min_feedback,
            triggered_by='threshold',
        )
        if variant:
            logger.info(
                f"[AutoImprove] Threshold: created variant {variant.id} for "
                f"{prompt_type} (new_feedback={new_count})"
            )
    except Exception:
        logger.exception(f"[AutoImprove] Threshold run failed for {prompt_type}")
