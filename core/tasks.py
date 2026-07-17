# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from celery import shared_task
from core.models import Course
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@shared_task
def finalize_expired_quiz_attempts():
    """Auto-submit + grade timed quiz attempts whose deadline has passed but were never
    submitted (e.g. the student closed the tab). The resume path already grades these when a
    student returns; this sweep catches the ones who never do, so a (partial) score isn't
    stuck in_progress forever.
    """
    from core.models import QuizAttempt
    from core.services import quiz_grading

    now = timezone.now()
    stuck = QuizAttempt.objects.filter(status='in_progress', deadline__isnull=False, deadline__lt=now)
    # Snapshot the ids first so grading (which mutates status out of the filter) can't disturb
    # the iteration, and isolate each attempt so one bad attempt can't strand all the others.
    count = 0
    for attempt_id in list(stuck.values_list('id', flat=True)):
        try:
            attempt = QuizAttempt.objects.get(pk=attempt_id, status='in_progress')
            quiz_grading.grade_attempt(attempt)
            count += 1
        except QuizAttempt.DoesNotExist:
            continue
        except Exception:
            logger.exception(f"Failed to finalize expired quiz attempt {attempt_id}")
    if count:
        logger.info(f"Finalized {count} expired quiz attempt(s)")
    return count

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

        service.set_request_context(
            user=submission.grader or submission.students.first(),
            request_type='suggested_comments',
        )
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
        service.set_request_context(
            user=submission.grader or submission.students.first(),
            request_type='submission_summary',
        )
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
                service.set_request_context(
                    user=submission.grader or submission.students.first(),
                    request_type='assignment_description',
                )
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


# --------------------------------------------------------------------------- #
# Quizzes
# --------------------------------------------------------------------------- #

def _parse_json_questions(text: str) -> list:
    """Parse a model's JSON array of questions, tolerating ```json fences."""
    import json
    cleaned = (text or '').strip()
    if cleaned.startswith('```'):
        # Strip a leading ```json / ``` fence and trailing ```.
        cleaned = cleaned.split('\n', 1)[-1] if '\n' in cleaned else cleaned
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    data = json.loads(cleaned)
    return data if isinstance(data, list) else []


def _normalize_choices(raw_choices) -> list:
    """Normalize AI choice entries to the {text, isCorrect, feedback} shape.

    Tolerates models that return choices as plain strings or use alternate keys
    (``value``/``answer`` for text, ``correct`` for correctness)."""
    out = []
    for c in raw_choices or []:
        if isinstance(c, str):
            out.append({'text': c, 'isCorrect': False, 'feedback': ''})
            continue
        if not isinstance(c, dict):
            continue
        text = c.get('text', c.get('value', c.get('answer', '')))
        is_correct = c.get('isCorrect', c.get('is_correct', c.get('correct', False)))
        out.append({
            'text': text or '',
            'isCorrect': bool(is_correct),
            'feedback': c.get('feedback', '') or '',
        })
    return out


@shared_task
def generate_quiz_question_suggestions(
    requested_by_id: int,
    assignment_id: int | None = None,
    source_question_id: int | None = None,
    num_questions: int = 5,
    question_types: list | None = None,
    instructions: str = '',
):
    """Generate AI quiz-question suggestions for an instructor to review and accept.

    Two entry points:
    - Fresh, assignment-seeded (``assignment_id``): clears prior pending suggestions
      for that assignment and proposes ``num_questions`` new questions.
    - Refresh, question-seeded (``source_question_id``): proposes one improved variant
      of an existing question (cross-semester update).
    """
    import uuid
    from asgiref.sync import async_to_sync
    from core.models import Assignment, Question, SuggestedQuizQuestion, User

    user = User.objects.filter(id=requested_by_id).first()
    assignment = Assignment.objects.filter(id=assignment_id).select_related(
        'course', 'course__organization').first() if assignment_id else None
    source_question = Question.objects.filter(id=source_question_id).select_related(
        'course', 'course__organization').first() if source_question_id else None

    course = (assignment.course if assignment else None) or (source_question.course if source_question else None)
    if course is None:
        logger.warning("[QuizGen] No course resolvable (assignment/source_question missing). Skipping.")
        return

    from core.services.ai_service import AIService
    service = AIService(course, assignment)
    if not service.is_configured or service.is_globally_disabled:
        logger.debug(f"[QuizGen] AI not configured/disabled for course {course.id}. Skipping.")
        return
    if not service.is_feature_enabled('quiz_generation'):
        logger.debug(f"[QuizGen] quiz_generation disabled for course {course.id}. Skipping.")
        return

    service.set_request_context(
        user=user, request_type='quiz_generation', instructions=instructions,
    )
    try:
        result = async_to_sync(service.generate_quiz_questions)(
            assignment=assignment,
            num_questions=num_questions,
            question_types=question_types,
            source_question=source_question,
            instructions=instructions,
        )
    except Exception as e:
        logger.error(f"[QuizGen] Generation failed for course {course.id}: {e}", exc_info=True)
        return

    if not result.success or not result.text:
        logger.warning(f"[QuizGen] Empty/failed generation for course {course.id}: {result.error}")
        service.record_usage(result, user=user, request_type='quiz_generation')
        return

    try:
        questions = _parse_json_questions(result.text)
    except Exception as e:
        logger.error(f"[QuizGen] Could not parse model output as JSON: {e}", exc_info=True)
        service.record_usage(result, user=user, request_type='quiz_generation')
        return

    batch = uuid.uuid4()
    prompt_variant_id = result.variant_id
    metadata = {
        'provider': service.provider,
        'model': service.model,
        'input_tokens': result.input_tokens,
        'output_tokens': result.output_tokens,
    }
    CHOICE_TYPES = {'multiple_choice', 'multiple_answers', 'true_false', 'short_answer', 'numerical'}
    created = 0
    missing_choices = 0
    from django.db import transaction
    with transaction.atomic():
        # Replace any prior pending suggestions for this seed (assignment for fresh generation,
        # or the source question for a refresh) so there's a single batch — but only now that
        # generation succeeded, so a failed/unparseable run leaves the existing queue intact.
        if source_question is not None:
            SuggestedQuizQuestion.objects.filter(sourceQuestion=source_question, status='pending').delete()
        elif assignment is not None:
            SuggestedQuizQuestion.objects.filter(assignment=assignment, status='pending').delete()
        for q in questions:
            if not isinstance(q, dict) or not q.get('text'):
                continue
            qtype = q.get('type', 'multiple_choice')
            choices = _normalize_choices(q.get('choices') or q.get('options') or q.get('answers'))
            if qtype in CHOICE_TYPES and not choices:
                missing_choices += 1
            SuggestedQuizQuestion.objects.create(
                assignment=assignment,
                sourceQuestion=source_question,
                questionType=qtype,
                text=q.get('text', ''),
                choicesData=choices,
                points=q.get('points', 1) or 1,
                language=q.get('language') or (source_question.language if source_question else None),
                starterCode=q.get('starter_code'),
                referenceSolution=q.get('reference_solution'),
                generationMetadata=metadata,
                promptVariant_id=prompt_variant_id,
                generationBatch=batch,
            )
            created += 1

    logger.info(f"[QuizGen] Created {created} suggested quiz questions for course {course.id} (batch {batch})")
    if missing_choices:
        # Diagnostic: the model returned choice-type questions without choices. Logging the
        # raw output helps tell whether to adjust the active quiz_generation prompt variant.
        logger.warning(
            f"[QuizGen] {missing_choices}/{created} choice-type questions had no choices. "
            f"Raw model output (truncated): {(result.text or '')[:1500]}"
        )
    service.record_usage(result, user=user, request_type='quiz_generation')


@shared_task
def generate_personalized_quiz_sets(
    submission_id: int | None = None,
    quiz_id: int | None = None,
    force: bool = False,
    requested_by_id: int | None = None,
    student_id: int | None = None,
):
    """Generate per-student quiz questions for the generated sections of the quizzes
    attached to this submission's assignment.

    Triggered on submission upload (signals.auto_generate_personalized_quiz) and by the
    staff "regenerate" / "generate for student" actions (``quiz_id`` + ``force=True``).
    One AI call per section; a group submission gets one generation copied into one set
    per member — unless ``student_id`` scopes the run to a single member (the staff
    actions target one student and must not touch a group-mate's set). A student's set
    is skipped once approved unless ``force`` (regenerate-unless-published). Each run
    claims its sets with a ``generationBatch`` UUID — a task whose batch has been
    superseded by a newer run (resubmission while generating) discards its results.

    With ``submission_id=None`` (``quiz_id`` + ``student_id`` required) the run is
    submission-less: the eager path for quizzes whose prompts don't draw on submission
    data — including standalone quizzes with no assignment at all.
    """
    import uuid
    from core.models import Quiz, Submission, User
    from core.services.quiz_grading import generation_needs_submission

    if submission_id is None:
        # Submission-less (eager) generation: one student on one quiz.
        if quiz_id is None or student_id is None:
            logger.warning("[PersonalQuizGen] Submission-less run needs quiz_id and student_id. Skipping.")
            return
        quiz = Quiz.objects.filter(id=quiz_id).select_related(
            'course', 'course__organization', 'assignment').prefetch_related(
            'generatedSections').first()
        student = User.objects.filter(id=student_id).first()
        if quiz is None or quiz.course.archived or student is None:
            return
        submission = None
        assignment = quiz.assignment
        course = quiz.course
        students = [student]
        quizzes = [quiz] if quiz.generatedSections.exists() else []
    else:
        submission = Submission.objects.filter(id=submission_id).select_related(
            'assignment', 'assignment__course', 'assignment__course__organization').first()
        if submission is None:
            logger.warning(f"[PersonalQuizGen] Submission {submission_id} not found. Skipping.")
            return
        assignment = submission.assignment
        course = assignment.course
        if course.archived:
            return
        students = list(submission.students.all())
        if student_id is not None:
            students = [s for s in students if s.id == student_id]

        quiz_qs = assignment.quizzes.filter(generatedSections__isnull=False).distinct()
        if quiz_id is not None:
            quiz_qs = quiz_qs.filter(id=quiz_id)
        quizzes = list(quiz_qs.prefetch_related('generatedSections'))
    if not students or not quizzes:
        return
    # Code questions need a language for syntax highlighting; the model's output has no
    # language field, so default from the assignment's environment.
    try:
        env_language = (assignment.environment.language or '') if assignment else ''
    except Exception:
        env_language = ''

    from core.services.ai_service import AIService
    service = AIService(course, assignment)
    if not service.is_configured or service.is_globally_disabled:
        logger.debug(f"[PersonalQuizGen] AI not configured/disabled for course {course.id}. Skipping.")
        return
    if not service.is_feature_enabled('personalized_quiz_generation'):
        logger.debug(f"[PersonalQuizGen] personalized_quiz_generation disabled for course {course.id}. Skipping.")
        return

    user = User.objects.filter(id=requested_by_id).first() if requested_by_id else None
    service.set_request_context(user=user, request_type='personalized_quiz_generation')

    for quiz in quizzes:
        target_students = students
        if submission is not None and not force and not generation_needs_submission(quiz):
            # Submission-free quiz: an upload doesn't change its questions — only fill
            # gaps (e.g. a student who enrolled after the eager backfill ran).
            target_students = [s for s in students
                               if not quiz.generatedSets.filter(student=s).exists()]
            if not target_students:
                continue
        batch = uuid.uuid4()
        claimed_ids = _claim_generation_sets(quiz, target_students, submission, force, batch)
        if not claimed_ids:
            continue
        question_rows, error, variant_id, metadata = _generate_quiz_question_rows(
            service, quiz, submission, env_language, user)
        _write_generation_results(quiz, claimed_ids, batch, question_rows, error,
                                  variant_id, metadata)
        logger.info(
            f"[PersonalQuizGen] Quiz {quiz.id}: {'failed' if error else 'generated'} "
            f"{len(question_rows)} questions for {len(claimed_ids)} student(s) (batch {batch})")


_CHOICE_TYPES = {'multiple_choice', 'multiple_answers', 'true_false', 'short_answer', 'numerical'}


def _claim_generation_sets(quiz, students, submission, force, batch):
    """Claim one set per student, stamped with this run's batch UUID. Approved sets are
    skipped unless ``force``. Returns the claimed set ids."""
    from django.db import transaction
    from core.models import GeneratedQuestionSet

    claimed_ids = []
    with transaction.atomic():
        for student in students:
            gen_set, _ = GeneratedQuestionSet.objects.get_or_create(quiz=quiz, student=student)
            if gen_set.status == 'approved' and not force:
                continue
            gen_set.status = 'generating'
            gen_set.submission = submission
            gen_set.generationBatch = batch
            gen_set.errorMessage = ''
            gen_set.approvedBy = None
            gen_set.approvedAt = None
            gen_set.save(update_fields=['status', 'submission', 'generationBatch',
                                        'errorMessage', 'approvedBy', 'approvedAt', 'modified'])
            claimed_ids.append(gen_set.id)
    return claimed_ids


def _generate_quiz_question_rows(service, quiz, submission, env_language, user):
    """Run one AI call per section and normalize the output into question rows.

    Returns ``(question_rows, error, variant_id, metadata)`` — any failure fails the
    whole set (no partial sets), reported through ``error``."""
    from asgiref.sync import async_to_sync

    question_rows: list[tuple] = []  # (section, normalized question dict)
    error = ''
    variant_id = None
    input_tokens = output_tokens = 0
    section_prompts = []  # what the model actually saw, for staff review on the set
    for section in quiz.generatedSections.all():
        try:
            result = async_to_sync(service.generate_personalized_quiz_questions)(section, submission)
        except Exception as e:
            logger.error(f"[PersonalQuizGen] Generation failed for quiz {quiz.id}: {e}", exc_info=True)
            error = f"Generation failed: {e}"
            break
        service.record_usage(result, user=user, request_type='personalized_quiz_generation')
        variant_id = result.variant_id or variant_id
        input_tokens += result.input_tokens
        output_tokens += result.output_tokens
        if result.resolved_prompt:
            section_prompts.append({
                'sectionId': section.id,
                'sectionName': section.name or '',
                # Bounded: a prompt embedding large submission files could be huge.
                'prompt': result.resolved_prompt[:100_000],
            })
        if not result.success or not result.text:
            error = result.error or 'Empty model response.'
            break
        try:
            parsed = _parse_json_questions(result.text)
        except Exception as e:
            logger.error(f"[PersonalQuizGen] Could not parse model output as JSON: {e}", exc_info=True)
            error = 'Could not parse the model output.'
            break
        section_rows = []
        for q in parsed:
            if not isinstance(q, dict) or not q.get('text'):
                continue
            qtype = q.get('type', 'multiple_choice')
            choices = _normalize_choices(q.get('choices') or q.get('options') or q.get('answers'))
            if qtype in _CHOICE_TYPES and not choices:
                logger.warning(
                    f"[PersonalQuizGen] Skipping a '{qtype}' question with no choices "
                    f"(quiz {quiz.id}). Raw output (truncated): {(result.text or '')[:1500]}")
                continue
            language = q.get('language')
            if qtype == 'code' and not language:
                language = env_language or None
            section_rows.append((section, {
                'questionType': qtype,
                'text': q.get('text', ''),
                'description': q.get('description', '') or '',
                'choicesData': choices,
                'language': language,
                'starterCode': q.get('starter_code'),
            }))
        if not section_rows:
            error = 'The model returned no usable questions.'
            break
        question_rows.extend(section_rows[:section.numQuestions])

    metadata = {
        'provider': service.provider,
        'model': service.model,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'sections': section_prompts,
    }
    return question_rows, error, variant_id, metadata


def _write_generation_results(quiz, claimed_ids, batch, question_rows, error,
                              variant_id, metadata):
    """Write questions/failure to the claimed sets — but only those our batch still owns
    (a resubmission that started a newer run wins; our stale results are discarded)."""
    from django.db import transaction
    from django.utils import timezone
    from core.models import GeneratedQuestionSet, GeneratedQuizQuestion

    auto_publish = quiz.autoPublishGenerated
    with transaction.atomic():
        gen_sets = list(GeneratedQuestionSet.objects.select_for_update().filter(
            id__in=claimed_ids, generationBatch=batch))
        for gen_set in gen_sets:
            gen_set.questions.all().delete()
            if error:
                gen_set.status = 'failed'
                gen_set.errorMessage = error
                gen_set.generationMetadata = metadata
                gen_set.save(update_fields=['status', 'errorMessage', 'generationMetadata', 'modified'])
                continue
            GeneratedQuizQuestion.objects.bulk_create([
                GeneratedQuizQuestion(
                    set=gen_set, section=section, sortKey=position,
                    points=section.pointsPerQuestion, **fields)
                for position, (section, fields) in enumerate(question_rows)
            ])
            gen_set.status = 'approved' if auto_publish else 'ready'
            gen_set.approvedAt = timezone.now() if auto_publish else None
            gen_set.generationMetadata = metadata
            gen_set.promptVariant_id = variant_id
            gen_set.save(update_fields=['status', 'approvedAt', 'generationMetadata',
                                        'promptVariant', 'modified'])


def enqueue_personalized_backfill(quiz, requested_by_id: int | None = None,
                                  missing_only: bool = False, dry_run: bool = False) -> int:
    """Enqueue per-student question generation for everyone who already submitted to the
    quiz's attached assignment. Returns the number of students queued.

    Covers sections created AFTER students started submitting — without this, early
    submitters have no GeneratedQuestionSet and sit on "being prepared" forever. With
    ``missing_only`` the run is restricted to students without a set (the review drawer's
    "Generate missing"); otherwise non-approved sets regenerate too, since a new section
    changes what every set should contain. Approved sets are never touched either way
    (the task's regenerate-unless-approved rule). ``dry_run`` only counts — it lets the
    UI warn the instructor how many students a new section would generate for.

    Quizzes whose prompts don't draw on submission data target every ENROLLED student
    instead (no submission needed) — the eager path, which also covers standalone
    quizzes with no assignment at all.

    Cheap to call inline (DB reads + .delay()s); the actual generation runs in the
    per-submission tasks. Group submissions are enqueued once (one shared AI call per
    section) unless only some members need generating.
    """
    from core.models import GeneratedQuestionSet
    from core.services.quiz_grading import LATEST_SUBMISSION_ORDERING, generation_needs_submission

    assignment = quiz.assignment
    has_sections = quiz.generatedSections.exists()
    if not dry_run and not has_sections:
        return 0
    # Previewing before the first section exists: the prompt is unknown, so assume the
    # submission-seeded path (the eager backfill on section save handles the rest).
    needs_submission = generation_needs_submission(quiz) if has_sections else True
    if assignment is None and needs_submission:
        return 0
    approved_or_all = GeneratedQuestionSet.objects.filter(quiz=quiz)
    if not missing_only:
        # Non-approved sets regenerate; only approved ones are protected.
        approved_or_all = approved_or_all.filter(status='approved')
    skip_ids = set(approved_or_all.values_list('student_id', flat=True))

    if not needs_submission:
        # Submission-free prompts: generate for every enrolled student, one task each.
        targets = quiz.course.students.exclude(id__in=skip_ids)
        queued = 0
        for student in targets:
            if not dry_run:
                generate_personalized_quiz_sets.delay(
                    quiz_id=quiz.id, student_id=student.id, requested_by_id=requested_by_id)
            queued += 1
        return queued

    # Newest submission wins per student (same rule as latest_submission_for).
    covered = set(skip_ids)
    queued = 0
    submissions = assignment.submissions.prefetch_related('students').order_by(
        *LATEST_SUBMISSION_ORDERING)
    for submission in submissions:
        members = list(submission.students.all())
        targets = [s for s in members if s.id not in covered]
        if not targets:
            continue
        covered.update(s.id for s in targets)
        if not dry_run:
            if len(targets) == len(members):
                generate_personalized_quiz_sets.delay(
                    submission.id, quiz_id=quiz.id, requested_by_id=requested_by_id)
            else:
                # Partial group (e.g. a partner already has a set): scope per student so
                # the covered member's set isn't touched.
                for s in targets:
                    generate_personalized_quiz_sets.delay(
                        submission.id, quiz_id=quiz.id, requested_by_id=requested_by_id,
                        student_id=s.id)
        queued += len(targets)
    return queued


@shared_task
def backfill_personalized_quiz_sets(quiz_id: int, requested_by_id: int | None = None):
    """Async wrapper around enqueue_personalized_backfill for signal-triggered backfills
    (a QuizGeneratedSection created after students already submitted)."""
    from core.models import Quiz

    quiz = Quiz.objects.filter(id=quiz_id).select_related('assignment').first()
    if quiz is None:
        return
    queued = enqueue_personalized_backfill(quiz, requested_by_id=requested_by_id)
    if queued:
        logger.info(f"[PersonalQuizGen] Backfill for quiz {quiz_id}: queued {queued} student(s).")


@shared_task
def import_quiz_qti(job_id: int, import_quizzes: bool = False):
    """Parse an uploaded Canvas QTI export and import its questions into a bank.

    By default only questions are imported (Canvas exports wrap question banks as
    ``<assessment>`` elements, so we would otherwise create surprise quizzes). When
    ``import_quizzes`` is True, any Canvas quizzes (assessments) are recreated too."""
    import io
    from decimal import Decimal
    from django.db import transaction
    from core.models import QuestionBank, Question, QuestionChoice, Quiz, QuizQuestion, QuizImportJob
    from core.services.canvas_qti_import import parse_canvas_export

    try:
        job = QuizImportJob.objects.select_related('course', 'targetBank').get(id=job_id)
    except QuizImportJob.DoesNotExist:
        logger.warning(f"[QuizImport] Job {job_id} not found. Skipping.")
        return

    job.status = 'running'
    job.save(update_fields=['status', 'modified'])

    try:
        with job.file.open('rb') as fh:
            raw = fh.read()
        parsed = parse_canvas_export(io.BytesIO(raw))

        with transaction.atomic():
            bank = job.targetBank
            if bank is None:
                bank, _ = QuestionBank.objects.get_or_create(
                    course=job.course,
                    name=f'Imported {job.created:%Y-%m-%d %H:%M}',
                    defaults={'source': 'imported', 'createdBy': job.createdBy},
                )

            # Content signature for dedup (consistent with the parser). Re-importing the
            # same export into a bank that already holds the questions reuses them rather
            # than creating duplicates.
            def _sig_db(question, choices):
                ch = tuple(sorted(((c.text or '').strip(), bool(c.isCorrect)) for c in choices))
                return (question.questionType, (question.text or '').strip(), ch)

            def _sig_parsed(q):
                ch = tuple(sorted(
                    ((c.get('text') or '').strip(), bool(c.get('isCorrect'))) for c in q.get('choices', [])
                ))
                return (q['type'], (q.get('text') or '').strip(), ch)

            existing_by_sig = {
                _sig_db(eq, list(eq.choices.all())): eq
                for eq in bank.questions.prefetch_related('choices')
            }

            ident_to_question: dict[str, Question] = {}
            created_count = 0
            reused_count = 0
            for q in parsed['questions']:
                sig = _sig_parsed(q)
                existing = existing_by_sig.get(sig)
                if existing is not None:
                    ident_to_question[q['ident']] = existing
                    reused_count += 1
                    continue
                question = Question.objects.create(
                    course=job.course,
                    bank=bank,
                    questionType=q['type'],
                    text=q['text'],
                    points=Decimal(str(q.get('points', 1))),
                    source='imported',
                    createdBy=job.createdBy,
                    metadata=q.get('metadata', {}),
                )
                for i, c in enumerate(q.get('choices', [])):
                    QuestionChoice.objects.create(
                        question=question,
                        text=c.get('text', ''),
                        isCorrect=bool(c.get('isCorrect')),
                        sortKey=i,
                        feedback=c.get('feedback', '') or '',
                    )
                existing_by_sig[sig] = question
                ident_to_question[q['ident']] = question
                created_count += 1

            quiz_count = 0
            if import_quizzes:
                for quiz_data in parsed['quizzes']:
                    quiz = Quiz.objects.create(
                        course=job.course,
                        title=quiz_data['title'] or 'Imported Quiz',
                        source='imported',
                        createdBy=job.createdBy,
                    )
                    seen_qids: set[int] = set()
                    for i, ident in enumerate(quiz_data['question_idents']):
                        question = ident_to_question.get(ident)
                        if question is not None and question.id not in seen_qids:
                            seen_qids.add(question.id)
                            QuizQuestion.objects.create(quiz=quiz, question=question, sortKey=i)
                    quiz_count += 1

            job.targetBank = bank
            job.createdQuestionCount = created_count
            job.createdQuizCount = quiz_count
            job.summary = {
                'imported_questions': created_count,
                'reused_questions': reused_count,
                'imported_quizzes': quiz_count,
                'skipped': parsed['skipped'],
            }
            job.status = 'completed'
            job.save()
        logger.info(f"[QuizImport] Job {job_id} completed: "
                    f"{job.createdQuestionCount} questions, {job.createdQuizCount} quizzes.")
    except Exception as e:
        logger.error(f"[QuizImport] Job {job_id} failed: {e}", exc_info=True)
        job.status = 'failed'
        job.errorMessage = str(e)
        job.save(update_fields=['status', 'errorMessage', 'modified'])
