# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""Tests for per-student AI-generated quiz questions: section authoring (+ prompt
validation), the submission-triggered generation task (claiming, regenerate-unless-
approved, stale-batch discard, auto-publish), the review/approve/publish API and its
grader-permission gate, student availability gating, and attempt materialization."""
import json
import uuid
from decimal import Decimal

import factory
import pytest
from django.db.models.signals import post_save
from django.utils import timezone
from rest_framework import status


QUESTIONS_JSON = json.dumps([
    {'type': 'multiple_choice', 'text': 'What does your helper return?', 'points': 2,
     'description': '```python\ndef helper():\n    return []\n```',
     'choices': [{'text': 'A list', 'is_correct': True}, {'text': 'None', 'is_correct': False}]},
    {'type': 'essay', 'text': 'Explain your loop.', 'points': 5, 'choices': []},
])


@pytest.fixture
def gen_setup(db):
    from core.tests.factories import CourseFactory, SubmissionFactory
    from core.models import Quiz, QuizGeneratedSection

    with factory.django.mute_signals(post_save):
        course = CourseFactory(name="cos226", period="s2026", organization__name="Princeton")
        assignment = course.assignments.first()
        assignment.isReleased = True
        assignment.save()
        students = list(course.students.all())
        submission = SubmissionFactory(assignment=assignment)
        submission.students.add(students[0])
        submission.dateUploaded = timezone.now()
        submission.save()

    quiz = Quiz.objects.create(course=course, title='Personalized Quiz', assignment=assignment,
                               isPublished=True, assignmentTrigger='after_submission')
    section = QuizGeneratedSection.objects.create(
        quiz=quiz, name='About your code', systemPrompt='Ask about {submission_files}.',
        numQuestions=2, pointsPerQuestion=Decimal('3'))
    return {
        'course': course,
        'assignment': assignment,
        'quiz': quiz,
        'section': section,
        'submission': submission,
        'admin': course.courseAdmins.first(),
        'grader': course.graders.first(),
        'students': students,
    }


def _mock_ai(monkeypatch, json_text=QUESTIONS_JSON, success=True, side_effect=None):
    from asgiref.sync import sync_to_async
    from core.services.ai_service import GenerationResult

    async def mock_generate(self, section, submission):
        if side_effect is not None:
            await sync_to_async(side_effect)(section, submission)
        if not success:
            return GenerationResult(text='', success=False, error='model unavailable')
        return GenerationResult(text=json_text, success=True, input_tokens=10, output_tokens=20)

    monkeypatch.setattr(
        'core.services.ai_service.AIService.generate_personalized_quiz_questions', mock_generate)
    monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
    monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: False))
    monkeypatch.setattr('core.services.ai_service.AIService.is_feature_enabled', lambda self, key: True)
    monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)


def _run_task(submission, **kwargs):
    from core.tasks import generate_personalized_quiz_sets
    generate_personalized_quiz_sets(submission.id, **kwargs)


def _make_set(quiz, student, submission=None, status='ready', questions=True):
    """Create a generated set (and questions) directly, bypassing the task."""
    from core.models import GeneratedQuestionSet, GeneratedQuizQuestion
    gen_set = GeneratedQuestionSet.objects.create(
        quiz=quiz, student=student, submission=submission, status=status,
        approvedAt=timezone.now() if status == 'approved' else None)
    if questions:
        section = quiz.generatedSections.first()
        GeneratedQuizQuestion.objects.create(
            set=gen_set, section=section, questionType='multiple_choice',
            text='About your code?', points=Decimal('3'), sortKey=0,
            choicesData=[{'text': 'Right', 'isCorrect': True, 'feedback': ''},
                         {'text': 'Wrong', 'isCorrect': False, 'feedback': ''}])
        GeneratedQuizQuestion.objects.create(
            set=gen_set, section=section, questionType='essay',
            text='Explain it.', points=Decimal('3'), sortKey=1)
    return gen_set


# --------------------------------------------------------------------------- #
# Section authoring
# --------------------------------------------------------------------------- #

def _feature_on(monkeypatch):
    """Creating a section requires the personalized_quiz_generation feature; tests run
    without an AI provider, so enable it explicitly where creation should succeed."""
    monkeypatch.setattr('core.services.ai_service.AIService.is_feature_enabled',
                        lambda self, key: True)


class TestSectionAuthoring:
    def test_staff_can_create_section(self, api_client, gen_setup, monkeypatch):
        _feature_on(monkeypatch)
        api_client.force_authenticate(user=gen_setup['grader'])
        resp = api_client.post('/quizGeneratedSections/', {
            'quiz': gen_setup['quiz'].id, 'systemPrompt': 'Ask about {assignment_name}.',
            'numQuestions': 3, 'pointsPerQuestion': '2.00',
        }, format='json')
        assert resp.status_code == status.HTTP_201_CREATED

    def test_student_cannot_create_section(self, api_client, gen_setup, monkeypatch):
        _feature_on(monkeypatch)
        api_client.force_authenticate(user=gen_setup['students'][0])
        resp = api_client.post('/quizGeneratedSections/', {
            'quiz': gen_setup['quiz'].id, 'systemPrompt': 'x',
        }, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_create_blocked_when_feature_disabled(self, api_client, gen_setup):
        # No AI provider is configured in tests, so the feature resolves to disabled.
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post('/quizGeneratedSections/', {
            'quiz': gen_setup['quiz'].id, 'systemPrompt': 'x',
        }, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'not enabled' in str(resp.data)

    def test_editing_section_allowed_when_feature_disabled(self, api_client, gen_setup):
        # Editing/deleting existing sections stays possible for cleanup after a
        # course turns the feature off.
        api_client.force_authenticate(user=gen_setup['admin'])
        section = gen_setup['section']
        resp = api_client.patch(f'/quizGeneratedSections/{section.id}/',
                                {'numQuestions': 5}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        delete = api_client.delete(f'/quizGeneratedSections/{section.id}/')
        assert delete.status_code == status.HTTP_204_NO_CONTENT

    def test_unknown_variable_rejected(self, api_client, gen_setup, monkeypatch):
        _feature_on(monkeypatch)
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post('/quizGeneratedSections/', {
            'quiz': gen_setup['quiz'].id, 'systemPrompt': 'Use {not_a_variable}.',
        }, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Unknown variable' in str(resp.data)

    def test_unattached_quiz_rejected(self, api_client, gen_setup, monkeypatch):
        from core.models import Quiz
        _feature_on(monkeypatch)
        standalone = Quiz.objects.create(course=gen_setup['course'], title='Standalone')
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post('/quizGeneratedSections/', {
            'quiz': standalone.id, 'systemPrompt': 'x',
        }, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_change_assignment_with_sections(self, api_client, gen_setup):
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.patch(f"/quizzes/{gen_setup['quiz'].id}/",
                                {'assignment': None}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_prompt_variables_endpoint(self, api_client, gen_setup):
        from core.tests.factories import AssignmentFileFactory
        with factory.django.mute_signals(post_save):
            AssignmentFileFactory(assignment=gen_setup['assignment'], name='main.py', data='x')
        api_client.force_authenticate(user=gen_setup['grader'])
        resp = api_client.get(f"/quizzes/{gen_setup['quiz'].id}/promptVariables/")
        assert resp.status_code == status.HTTP_200_OK
        tokens = {e['token'] for e in resp.data}
        assert '{submission_files}' in tokens
        assert '{assignment_file:main.py}' in tokens

    def test_prompt_variables_forbidden_for_students(self, api_client, gen_setup):
        api_client.force_authenticate(user=gen_setup['students'][0])
        resp = api_client.get(f"/quizzes/{gen_setup['quiz'].id}/promptVariables/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------- #
# Submission signal
# --------------------------------------------------------------------------- #

class TestSubmissionSignal:
    def _fire(self, submission, monkeypatch, created=True, update_fields=None):
        from core.models import Submission
        from core.signals import auto_generate_personalized_quiz
        calls = []
        monkeypatch.setattr('core.tasks.generate_personalized_quiz_sets.apply_async',
                            lambda *a, **kw: calls.append((a, kw)))
        auto_generate_personalized_quiz(Submission, submission, created,
                                        update_fields=update_fields)
        return calls

    def test_enqueues_on_creation(self, gen_setup, monkeypatch):
        assert len(self._fire(gen_setup['submission'], monkeypatch, created=True)) == 1

    def test_enqueues_on_file_upload(self, gen_setup, monkeypatch):
        calls = self._fire(gen_setup['submission'], monkeypatch, created=False,
                           update_fields=frozenset({'dateUploaded'}))
        assert len(calls) == 1

    def test_skips_other_updates(self, gen_setup, monkeypatch):
        calls = self._fire(gen_setup['submission'], monkeypatch, created=False,
                           update_fields=frozenset({'grade'}))
        assert calls == []

    def test_skips_without_generated_sections(self, gen_setup, monkeypatch):
        gen_setup['section'].delete()
        assert self._fire(gen_setup['submission'], monkeypatch, created=True) == []


# --------------------------------------------------------------------------- #
# Generation task
# --------------------------------------------------------------------------- #

class TestGenerationTask:
    def test_generates_ready_set(self, gen_setup, monkeypatch):
        _mock_ai(monkeypatch)
        _run_task(gen_setup['submission'])
        gen_set = gen_setup['quiz'].generatedSets.get(student=gen_setup['students'][0])
        assert gen_set.status == 'ready'
        assert gen_set.submission_id == gen_setup['submission'].id
        questions = list(gen_set.questions.all())
        assert len(questions) == 2
        # Points come from the section (not the model output); order is preserved.
        assert all(q.points == Decimal('3') for q in questions)
        assert questions[0].questionType == 'multiple_choice'
        assert questions[0].choicesData[0]['isCorrect'] is True
        # The model's Markdown description (e.g. the referenced code excerpt) is kept.
        assert questions[0].description.startswith('```python')
        assert questions[1].description == ''

    def test_feature_disabled_skips(self, gen_setup, monkeypatch):
        _mock_ai(monkeypatch)
        monkeypatch.setattr('core.services.ai_service.AIService.is_feature_enabled',
                            lambda self, key: False)
        _run_task(gen_setup['submission'])
        assert gen_setup['quiz'].generatedSets.count() == 0

    def test_auto_publish_approves(self, gen_setup, monkeypatch):
        quiz = gen_setup['quiz']
        quiz.autoPublishGenerated = True
        quiz.save()
        _mock_ai(monkeypatch)
        _run_task(gen_setup['submission'])
        gen_set = quiz.generatedSets.get(student=gen_setup['students'][0])
        assert gen_set.status == 'approved'
        assert gen_set.approvedBy is None and gen_set.approvedAt is not None

    def test_approved_set_not_regenerated(self, gen_setup, monkeypatch):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0], status='approved')
        question_ids = set(gen_set.questions.values_list('id', flat=True))
        _mock_ai(monkeypatch)
        _run_task(gen_setup['submission'])
        gen_set.refresh_from_db()
        assert gen_set.status == 'approved'
        assert set(gen_set.questions.values_list('id', flat=True)) == question_ids

    def test_force_regenerates_approved_set(self, gen_setup, monkeypatch):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0],
                            submission=gen_setup['submission'], status='approved')
        _mock_ai(monkeypatch)
        _run_task(gen_setup['submission'], quiz_id=gen_setup['quiz'].id, force=True)
        gen_set.refresh_from_db()
        assert gen_set.status == 'ready'
        assert gen_set.approvedAt is None

    def test_ready_set_regenerated_on_resubmission(self, gen_setup, monkeypatch):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0], status='ready')
        old_ids = set(gen_set.questions.values_list('id', flat=True))
        _mock_ai(monkeypatch)
        _run_task(gen_setup['submission'])
        gen_set.refresh_from_db()
        assert gen_set.status == 'ready'
        assert set(gen_set.questions.values_list('id', flat=True)).isdisjoint(old_ids)

    def test_failed_generation_marks_failed(self, gen_setup, monkeypatch):
        _mock_ai(monkeypatch, success=False)
        _run_task(gen_setup['submission'])
        gen_set = gen_setup['quiz'].generatedSets.get(student=gen_setup['students'][0])
        assert gen_set.status == 'failed'
        assert 'model unavailable' in gen_set.errorMessage
        assert gen_set.questions.count() == 0

    def test_stale_batch_discards_results(self, gen_setup, monkeypatch):
        from core.models import GeneratedQuestionSet

        def newer_run_claims(section, submission):
            # While "our" run is generating, a newer run re-claims the set.
            GeneratedQuestionSet.objects.filter(quiz=section.quiz).update(
                generationBatch=uuid.uuid4())

        _mock_ai(monkeypatch, side_effect=newer_run_claims)
        _run_task(gen_setup['submission'])
        gen_set = gen_setup['quiz'].generatedSets.get(student=gen_setup['students'][0])
        # The stale run must not have written: still generating (as the newer run left it).
        assert gen_set.status == 'generating'
        assert gen_set.questions.count() == 0

    def test_code_question_defaults_environment_language(self, gen_setup, monkeypatch):
        from core.models import Environment
        Environment.objects.create(assignment=gen_setup['assignment'], language='python-3')
        _mock_ai(monkeypatch, json_text=json.dumps([
            {'type': 'code', 'text': 'Refactor your helper.', 'points': 3,
             'starter_code': 'def helper():\n    pass', 'choices': []},
        ]))
        _run_task(gen_setup['submission'])
        gen_set = gen_setup['quiz'].generatedSets.get(student=gen_setup['students'][0])
        question = gen_set.questions.get()
        assert question.questionType == 'code'
        assert question.language == 'python-3'
        assert question.starterCode == 'def helper():\n    pass'

    def test_group_submission_gets_one_set_per_member(self, gen_setup, monkeypatch):
        gen_setup['submission'].students.add(gen_setup['students'][1])
        _mock_ai(monkeypatch)
        _run_task(gen_setup['submission'])
        sets = list(gen_setup['quiz'].generatedSets.all())
        assert len(sets) == 2
        assert sets[0].generationBatch == sets[1].generationBatch
        assert all(s.questions.count() == 2 for s in sets)


class TestGenerateForStudent:
    """POST /quizzes/{id}/generateForStudent/ — staff-triggered generation for one
    student (testing a prompt / backfilling), scoped so group-mates are untouched."""

    def _eager_task(self, monkeypatch):
        from core.tasks import generate_personalized_quiz_sets
        monkeypatch.setattr('core.tasks.generate_personalized_quiz_sets.delay',
                            lambda *a, **kw: generate_personalized_quiz_sets(*a, **kw))

    def _post(self, api_client, gen_setup, email, force=False):
        return api_client.post(f"/quizzes/{gen_setup['quiz'].id}/generateForStudent/",
                               {'student': email, 'force': force}, format='json')

    def test_generates_for_one_student(self, api_client, gen_setup, monkeypatch):
        _mock_ai(monkeypatch)
        self._eager_task(monkeypatch)
        # Group submission: generating for students[0] must not touch students[1].
        gen_setup['submission'].students.add(gen_setup['students'][1])
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = self._post(api_client, gen_setup, gen_setup['students'][0].email)
        assert resp.status_code == status.HTTP_202_ACCEPTED
        gen_set = gen_setup['quiz'].generatedSets.get(student=gen_setup['students'][0])
        assert gen_set.status == 'ready'
        assert gen_set.questions.count() == 2
        assert not gen_setup['quiz'].generatedSets.filter(
            student=gen_setup['students'][1]).exists()

    def test_approved_needs_force(self, api_client, gen_setup, monkeypatch):
        _mock_ai(monkeypatch)
        self._eager_task(monkeypatch)
        _make_set(gen_setup['quiz'], gen_setup['students'][0],
                  submission=gen_setup['submission'], status='approved')
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = self._post(api_client, gen_setup, gen_setup['students'][0].email)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'force' in str(resp.data)
        resp = self._post(api_client, gen_setup, gen_setup['students'][0].email, force=True)
        assert resp.status_code == status.HTTP_202_ACCEPTED
        gen_set = gen_setup['quiz'].generatedSets.get(student=gen_setup['students'][0])
        assert gen_set.status == 'ready'
        assert gen_set.approvedAt is None

    def test_requires_submission(self, api_client, gen_setup, monkeypatch):
        _mock_ai(monkeypatch)
        api_client.force_authenticate(user=gen_setup['admin'])
        # students[1] never submitted.
        resp = self._post(api_client, gen_setup, gen_setup['students'][1].email)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'no submission' in str(resp.data)

    def test_unknown_or_unenrolled_email_rejected(self, api_client, gen_setup, monkeypatch):
        _mock_ai(monkeypatch)
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = self._post(api_client, gen_setup, 'nobody@example.com')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        resp = self._post(api_client, gen_setup, gen_setup['grader'].email)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_feature_disabled_rejected(self, api_client, gen_setup):
        # No AI provider configured in tests → feature resolves to disabled.
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = self._post(api_client, gen_setup, gen_setup['students'][0].email)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'not enabled' in str(resp.data)

    def test_grader_gate_follows_quiz_flag(self, api_client, gen_setup, monkeypatch):
        _mock_ai(monkeypatch)
        self._eager_task(monkeypatch)
        api_client.force_authenticate(user=gen_setup['grader'])
        resp = self._post(api_client, gen_setup, gen_setup['students'][0].email)
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        gen_setup['quiz'].gradersCanReviewGenerated = True
        gen_setup['quiz'].save()
        resp = self._post(api_client, gen_setup, gen_setup['students'][0].email)
        assert resp.status_code == status.HTTP_202_ACCEPTED

    def test_student_forbidden(self, api_client, gen_setup, monkeypatch):
        _mock_ai(monkeypatch)
        api_client.force_authenticate(user=gen_setup['students'][0])
        resp = self._post(api_client, gen_setup, gen_setup['students'][0].email)
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------- #
# Review / approve / publish API + permission gate
# --------------------------------------------------------------------------- #

class TestReviewAPI:
    def test_admin_lists_sets(self, api_client, gen_setup):
        _make_set(gen_setup['quiz'], gen_setup['students'][0])
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.get(f"/quizzes/{gen_setup['quiz'].id}/generatedSets/")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1
        assert resp.data[0]['questionCount'] == 2

    def test_grader_gate_follows_quiz_flag(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0])
        api_client.force_authenticate(user=gen_setup['grader'])
        assert api_client.get(f"/quizzes/{gen_setup['quiz'].id}/generatedSets/") \
            .status_code == status.HTTP_403_FORBIDDEN
        assert api_client.post(f"/generatedQuestionSets/{gen_set.id}/approve/") \
            .status_code == status.HTTP_403_FORBIDDEN

        gen_setup['quiz'].gradersCanReviewGenerated = True
        gen_setup['quiz'].save()
        assert api_client.get(f"/quizzes/{gen_setup['quiz'].id}/generatedSets/") \
            .status_code == status.HTTP_200_OK
        resp = api_client.post(f"/generatedQuestionSets/{gen_set.id}/approve/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['status'] == 'approved'

    def test_student_never_accesses_sets(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0])
        api_client.force_authenticate(user=gen_setup['students'][0])
        assert api_client.get(f"/quizzes/{gen_setup['quiz'].id}/generatedSets/") \
            .status_code == status.HTTP_403_FORBIDDEN
        assert api_client.get(f"/generatedQuestionSets/{gen_set.id}/") \
            .status_code == status.HTTP_403_FORBIDDEN

    def test_approve_requires_questions(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0], questions=False)
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post(f"/generatedQuestionSets/{gen_set.id}/approve/")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_approve_sets_approver(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0])
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post(f"/generatedQuestionSets/{gen_set.id}/approve/")
        assert resp.status_code == status.HTTP_200_OK
        gen_set.refresh_from_db()
        assert gen_set.approvedBy == gen_setup['admin']

    def test_unapprove_blocked_after_attempt(self, api_client, gen_setup):
        from core.models import QuizAttempt
        student = gen_setup['students'][0]
        gen_set = _make_set(gen_setup['quiz'], student, status='approved')
        QuizAttempt.objects.create(quiz=gen_setup['quiz'], student=student, attemptNumber=1,
                                   startedAt=timezone.now())
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post(f"/generatedQuestionSets/{gen_set.id}/unapprove/")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unapprove_reopens_review(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0], status='approved')
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post(f"/generatedQuestionSets/{gen_set.id}/unapprove/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['status'] == 'ready'

    def test_regenerate_requires_submission(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0], submission=None)
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post(f"/generatedQuestionSets/{gen_set.id}/regenerate/")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_regenerate_enqueues_forced_run(self, api_client, gen_setup, monkeypatch):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0],
                            submission=gen_setup['submission'], status='approved')
        calls = []
        monkeypatch.setattr('core.tasks.generate_personalized_quiz_sets.delay',
                            lambda *a, **kw: calls.append((a, kw)))
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post(f"/generatedQuestionSets/{gen_set.id}/regenerate/")
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert resp.data['status'] == 'pending'
        assert len(calls) == 1 and calls[0][1]['force'] is True

    def test_publish_all_is_admin_only(self, api_client, gen_setup):
        gen_setup['quiz'].gradersCanReviewGenerated = True
        gen_setup['quiz'].save()
        _make_set(gen_setup['quiz'], gen_setup['students'][0])
        api_client.force_authenticate(user=gen_setup['grader'])
        assert api_client.post(f"/quizzes/{gen_setup['quiz'].id}/publishAllGenerated/") \
            .status_code == status.HTTP_403_FORBIDDEN

    def test_publish_all_approves_ready_sets(self, api_client, gen_setup):
        _make_set(gen_setup['quiz'], gen_setup['students'][0])
        _make_set(gen_setup['quiz'], gen_setup['students'][1], questions=False)  # skipped
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post(f"/quizzes/{gen_setup['quiz'].id}/publishAllGenerated/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == {'approved': 1, 'skipped': 1}

    def test_edit_generated_question(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0])
        question = gen_set.questions.first()
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.patch(f"/generatedQuizQuestions/{question.id}/", {
            'text': 'Improved stem',
            'choicesData': [{'text': 'A', 'isCorrect': True}, {'text': 'B', 'isCorrect': False}],
        }, format='json')
        assert resp.status_code == status.HTTP_200_OK
        question.refresh_from_db()
        assert question.text == 'Improved stem'
        assert question.choicesData[0] == {'text': 'A', 'isCorrect': True, 'feedback': ''}

    def test_edit_gate_follows_quiz_flag(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0])
        question = gen_set.questions.first()
        api_client.force_authenticate(user=gen_setup['grader'])
        resp = api_client.patch(f"/generatedQuizQuestions/{question.id}/",
                                {'text': 'nope'}, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_edit_blocked_while_generating(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0], status='generating')
        question = gen_set.questions.first()
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.patch(f"/generatedQuizQuestions/{question.id}/",
                                {'text': 'nope'}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_generated_question(self, api_client, gen_setup):
        gen_set = _make_set(gen_setup['quiz'], gen_setup['students'][0])
        question = gen_set.questions.first()
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.delete(f"/generatedQuizQuestions/{question.id}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert gen_set.questions.count() == 1


# --------------------------------------------------------------------------- #
# Student availability + attempt materialization
# --------------------------------------------------------------------------- #

class TestStudentTaking:
    def _available(self, api_client, gen_setup):
        resp = api_client.get(f"/quizAttempts/availableQuizzes/?course={gen_setup['course'].id}")
        assert resp.status_code == status.HTTP_200_OK
        return {q['id']: q for q in resp.data}

    def test_locked_until_set_approved(self, api_client, gen_setup):
        student = gen_setup['students'][0]
        api_client.force_authenticate(user=student)
        quizzes = self._available(api_client, gen_setup)
        assert quizzes[gen_setup['quiz'].id]['availability'] == {
            'isOpen': False, 'reason': 'questions_not_ready'}
        # Starting is blocked too.
        resp = api_client.post('/quizAttempts/', {'quiz': gen_setup['quiz'].id}, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert 'questions_not_ready' in resp.data['detail']

        _make_set(gen_setup['quiz'], student, status='approved')
        quizzes = self._available(api_client, gen_setup)
        assert quizzes[gen_setup['quiz'].id]['availability'] == {'isOpen': True, 'reason': 'open'}
        assert quizzes[gen_setup['quiz'].id]['questionCount'] == 2

    def test_question_count_estimates_before_approval(self, api_client, gen_setup):
        api_client.force_authenticate(user=gen_setup['students'][0])
        quizzes = self._available(api_client, gen_setup)
        # No approved set yet: the section's configured count.
        assert quizzes[gen_setup['quiz'].id]['questionCount'] == 2

    def test_attempt_materializes_generated_questions(self, api_client, gen_setup):
        from core.models import Question, QuestionBank, QuizQuestion
        course, quiz, student = gen_setup['course'], gen_setup['quiz'], gen_setup['students'][0]
        # One fixed question + the student's approved generated set (MC + essay).
        bank = QuestionBank.objects.create(course=course, name='Bank')
        fixed = Question.objects.create(course=course, bank=bank, questionType='true_false',
                                        text='Fixed?', points=Decimal('1'))
        fixed.choices.create(text='True', isCorrect=True, sortKey=0)
        fixed.choices.create(text='False', isCorrect=False, sortKey=1)
        QuizQuestion.objects.create(quiz=quiz, question=fixed, sortKey=0)
        _make_set(quiz, student, status='approved')

        api_client.force_authenticate(user=student)
        resp = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        responses = resp.data['responses']
        assert len(responses) == 3

        by_text = {r['question']['text']: r for r in responses}
        generated_mc = by_text['About your code?']
        # Generated responses carry no live question id, and choices use synthetic ids.
        assert generated_mc['question']['id'] is None
        choice_ids = [c['id'] for c in generated_mc['question']['choices']]
        assert choice_ids == [1, 2]
        # No answer key or provenance leaks pre-reveal.
        assert 'isCorrect' not in generated_mc['question']['choices'][0]
        payload = resp.content.decode()
        for banned in ('generationMetadata', 'promptVariant', 'generationBatch', '"source"'):
            assert banned not in payload

        # Answer the generated MC correctly and submit: auto-graded from the snapshot.
        attempt_id = resp.data['id']
        save = api_client.patch(f"/quizAttempts/{attempt_id}/saveAnswer/", {
            'response': generated_mc['id'], 'selectedChoices': [1]}, format='json')
        assert save.status_code == status.HTTP_200_OK
        submit = api_client.post(f"/quizAttempts/{attempt_id}/submit/")
        assert submit.status_code == status.HTTP_200_OK
        # Generated MC (3 pts, correct) counts; essay (3 pts) needs manual grading; the
        # unanswered fixed question (1 pt) is wrong.
        assert Decimal(submit.data['score']) == Decimal('3')
        assert Decimal(submit.data['maxScore']) == Decimal('7')

    def test_edits_after_start_do_not_change_attempt(self, api_client, gen_setup):
        student = gen_setup['students'][0]
        gen_set = _make_set(gen_setup['quiz'], student, status='approved')
        api_client.force_authenticate(user=student)
        resp = api_client.post('/quizAttempts/', {'quiz': gen_setup['quiz'].id}, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        question = gen_set.questions.first()
        question.text = 'Changed after start'
        question.save()
        again = api_client.get(f"/quizAttempts/{resp.data['id']}/")
        texts = {r['question']['text'] for r in again.data['responses']}
        assert 'Changed after start' not in texts


# --------------------------------------------------------------------------- #
# Backfill: sections created after students already submitted
# --------------------------------------------------------------------------- #

class TestBackfill:
    def _eager_tasks(self, monkeypatch):
        """No broker in tests — run the queued tasks inline (same pattern as
        TestGenerateForStudent)."""
        from core.tasks import backfill_personalized_quiz_sets, generate_personalized_quiz_sets
        monkeypatch.setattr('core.tasks.generate_personalized_quiz_sets.delay',
                            lambda *a, **kw: generate_personalized_quiz_sets(*a, **kw))
        monkeypatch.setattr('core.tasks.backfill_personalized_quiz_sets.delay',
                            lambda *a, **kw: backfill_personalized_quiz_sets(*a, **kw))

    def test_section_created_after_submissions_backfills(self, api_client, gen_setup, monkeypatch):
        """A section added late (students already submitted) generates sets for those
        students immediately — they must not sit on 'being prepared' forever."""
        from core.models import GeneratedQuestionSet, Quiz
        _mock_ai(monkeypatch)
        self._eager_tasks(monkeypatch)
        late_quiz = Quiz.objects.create(course=gen_setup['course'], title='Late quiz',
                                        assignment=gen_setup['assignment'])
        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post('/quizGeneratedSections/', {
            'quiz': late_quiz.id, 'systemPrompt': 'Ask about {submission_files}.',
            'numQuestions': 2, 'pointsPerQuestion': '3.00',
        }, format='json')
        assert resp.status_code == status.HTTP_201_CREATED

        # Celery runs eagerly in tests: the backfill already generated for the fixture's submitter.
        gen_set = GeneratedQuestionSet.objects.get(quiz=late_quiz, student=gen_setup['students'][0])
        assert gen_set.status == 'ready'
        assert gen_set.questions.count() > 0
        # Students without a submission get nothing.
        assert not GeneratedQuestionSet.objects.filter(
            quiz=late_quiz, student=gen_setup['students'][1]).exists()

    def test_generate_missing_targets_only_students_without_sets(self, api_client, gen_setup, monkeypatch):
        from core.models import GeneratedQuestionSet
        from core.tests.factories import SubmissionFactory
        _mock_ai(monkeypatch)
        self._eager_tasks(monkeypatch)
        # A second submitter, added with signals muted (i.e. generation never ran for them).
        with factory.django.mute_signals(post_save):
            sub2 = SubmissionFactory(assignment=gen_setup['assignment'])
            sub2.students.add(gen_setup['students'][1])
            sub2.dateUploaded = timezone.now()
            sub2.save()
        # The first submitter already has an APPROVED set — it must stay untouched.
        existing = _make_set(gen_setup['quiz'], gen_setup['students'][0],
                             submission=gen_setup['submission'], status='approved')

        api_client.force_authenticate(user=gen_setup['admin'])
        resp = api_client.post(f"/quizzes/{gen_setup['quiz'].id}/generateMissing/", {}, format='json')
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert resp.data['queued'] == 1

        missing = GeneratedQuestionSet.objects.get(quiz=gen_setup['quiz'],
                                                   student=gen_setup['students'][1])
        assert missing.status == 'ready'
        existing.refresh_from_db()
        assert existing.status == 'approved'  # not regenerated

        # Everyone covered now: a second run queues nothing.
        again = api_client.post(f"/quizzes/{gen_setup['quiz'].id}/generateMissing/", {}, format='json')
        assert again.status_code == status.HTTP_202_ACCEPTED
        assert again.data['queued'] == 0

    def test_generate_missing_permissions_and_feature_gate(self, api_client, gen_setup, monkeypatch):
        # Plain graders (without the review flag) and students are blocked.
        api_client.force_authenticate(user=gen_setup['grader'])
        assert api_client.post(f"/quizzes/{gen_setup['quiz'].id}/generateMissing/", {},
                               format='json').status_code == status.HTTP_403_FORBIDDEN
        api_client.force_authenticate(user=gen_setup['students'][0])
        assert api_client.post(f"/quizzes/{gen_setup['quiz'].id}/generateMissing/", {},
                               format='json').status_code == status.HTTP_403_FORBIDDEN
        # Admins get a clear 400 while the AI feature is off (no provider in tests).
        api_client.force_authenticate(user=gen_setup['admin'])
        off = api_client.post(f"/quizzes/{gen_setup['quiz'].id}/generateMissing/", {}, format='json')
        assert off.status_code == status.HTTP_400_BAD_REQUEST
        assert 'not enabled' in str(off.data)
