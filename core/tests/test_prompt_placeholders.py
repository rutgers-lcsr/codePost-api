# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for comment/summary prompt placeholders: the registry metadata, the
/promptTypes/ payload + access, the per-assignment override validation, and the
per-assignment submission-summary prompt override at generation time."""
import factory
import pytest
from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from rest_framework import status

from core.prompts.registry import (
    describe_prompt_placeholders,
    describe_prompt_templates,
    prompt_registry,
)


@pytest.fixture
def course_setup(db):
    from core.tests.factories import CourseFactory

    with factory.django.mute_signals(post_save):
        course = CourseFactory(name="cos217", period="s2026", organization__name="Princeton")
    assignment = course.assignments.first()
    submission = assignment.submissions.first()
    return {
        'course': course,
        'assignment': assignment,
        'submission': submission,
        'admin': course.courseAdmins.first(),
        'grader': course.graders.first(),
        'student': course.students.first(),
    }


class TestDescribePromptPlaceholders:
    def test_comment_placeholders_are_labeled(self):
        entries = describe_prompt_placeholders('comment_generation')
        by_token = {e['token']: e for e in entries}
        assert '{assignment_name}' in by_token
        assert '{all_files}' in by_token
        # The (auto)/(manual) semantic is carried in the label for the dropdown.
        assert '(manual)' in by_token['{all_files}']['label']
        assert '(auto)' in by_token['{file_content}']['label']
        assert all(e['kind'] == 'static' and e['argument'] is None for e in entries)

    def test_summary_placeholders(self):
        tokens = {e['token'] for e in describe_prompt_placeholders('submission_summary')}
        assert tokens == {
            '{assignment_name}', '{assignment_description}', '{test_results}',
            '{rubric}', '{description_comparison}',
        }

    def test_unenriched_type_falls_back_to_name_label(self):
        # test_generation was registered with a bare allowed_placeholders set.
        entries = describe_prompt_placeholders('test_generation')
        assert entries and all(e['label'] == e['name'] for e in entries)

    def test_allowed_placeholders_derived_from_placeholders(self):
        # The name frozenset (used by save-time validation) stays consistent.
        names = {e['name'] for e in describe_prompt_placeholders('comment_generation')}
        assert prompt_registry.get_allowed_placeholders('comment_generation') == names


class TestPromptTypesEndpoint:
    def test_accessible_to_non_superuser_with_placeholders(self, api_client, course_setup):
        # A course grader (authenticated, not a superuser/admin) can read the metadata.
        api_client.force_authenticate(user=course_setup['grader'])
        response = api_client.get('/promptTypes/')
        assert response.status_code == status.HTTP_200_OK
        by_key = {e['key']: e for e in response.data}
        assert 'comment_generation' in by_key
        assert 'submission_summary' in by_key
        tokens = {p['token'] for p in by_key['submission_summary']['placeholders']}
        assert '{assignment_description}' in tokens
        # Each type also carries starter templates, led by the synthesized 'basic' entry.
        comment_templates = {t['key'] for t in by_key['comment_generation']['templates']}
        assert 'basic' in comment_templates
        assert 'concise' in comment_templates

    def test_requires_authentication(self, api_client):
        response = api_client.get('/promptTypes/')
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class TestAssignmentPromptValidation:
    """Unit tests of the placeholder validator used by AssignmentSerializer."""

    def _validate(self, field, prompt_type, value):
        from core.serializers.assignment import AssignmentSerializer
        AssignmentSerializer._validate_prompt_placeholders({field: value}, field, prompt_type)

    def test_valid_summary_prompt_passes(self):
        self._validate('ai_summary_prompt', 'submission_summary',
                       'Summarize {assignment_name}. {rubric}')

    def test_unknown_summary_placeholder_rejected(self):
        from rest_framework import serializers
        with pytest.raises(serializers.ValidationError) as exc:
            self._validate('ai_summary_prompt', 'submission_summary', 'Use {file_content}')
        assert 'file_content' in str(exc.value)

    def test_unknown_comment_placeholder_rejected(self):
        from rest_framework import serializers
        with pytest.raises(serializers.ValidationError):
            self._validate('ai_system_prompt', 'comment_generation', 'Grade {not_a_var}')

    def test_blank_is_ignored(self):
        self._validate('ai_summary_prompt', 'submission_summary', '')

    def test_malformed_braces_rejected(self):
        from rest_framework import serializers
        with pytest.raises(serializers.ValidationError):
            self._validate('ai_summary_prompt', 'submission_summary', 'Broken {unclosed')

    def test_patch_round_trip(self, api_client, course_setup):
        # The AI fields are snake_case on the wire (no camelCase parser on this endpoint);
        # the generated TS client maps its camelCase property to this key.
        api_client.force_authenticate(user=course_setup['admin'])
        url = f"/assignments/{course_setup['assignment'].id}/"

        ok = api_client.patch(url, {'ai_summary_prompt': 'Summarize {assignment_name}.'}, format='json')
        assert ok.status_code == status.HTTP_200_OK
        course_setup['assignment'].refresh_from_db()
        assert course_setup['assignment'].ai_summary_prompt == 'Summarize {assignment_name}.'

        bad = api_client.patch(url, {'ai_summary_prompt': 'Summarize {bogus}.'}, format='json')
        assert bad.status_code == status.HTTP_400_BAD_REQUEST


class TestSummaryOverrideAtGeneration:
    def _run(self, course_setup, override_text):
        from core.services.ai_service import AIService, GenerationResult

        with factory.django.mute_signals(post_save):
            course_setup['assignment'].ai_summary_prompt = override_text
            course_setup['assignment'].save()

        captured = {}

        async def fake_generate(system_prompt, user_prompt, label=None):
            captured['system'] = system_prompt
            return GenerationResult(text='ok', success=True)

        svc = AIService(course_setup['course'], course_setup['assignment'])
        svc._generate = fake_generate  # type: ignore[method-assign]
        async_to_sync(svc.generate_submission_summary)(course_setup['submission'])
        return captured['system']

    def test_override_used_when_set(self, course_setup):
        name = course_setup['assignment'].name
        system = self._run(course_setup, 'CUSTOM SUMMARY for {assignment_name}')
        assert system == f'CUSTOM SUMMARY for {name}'

    def test_default_used_when_blank(self, course_setup):
        system = self._run(course_setup, '')
        # Falls back to the registered default template.
        assert 'CUSTOM SUMMARY' not in system
        assert 'grader' in system.lower()


class TestDescribePromptTemplates:
    def test_leads_with_basic_matching_default(self):
        for key in prompt_registry.keys():
            templates = describe_prompt_templates(key)
            assert templates, f'{key} has no templates'
            assert templates[0]['key'] == 'basic'
            assert templates[0]['text'] == prompt_registry.get_default_template(key)

    def test_curated_templates_included(self):
        keys = {t['key'] for t in describe_prompt_templates('comment_generation')}
        assert {'basic', 'concise', 'rubric-aligned'} <= keys
        summary_keys = {t['key'] for t in describe_prompt_templates('submission_summary')}
        assert {'basic', 'quick-triage', 'rubric-aligned'} <= summary_keys

    def test_all_template_text_uses_valid_placeholders(self):
        import string
        for key in prompt_registry.keys():
            allowed = prompt_registry.get_allowed_placeholders(key)
            if not allowed:
                continue
            for tpl in describe_prompt_templates(key):
                used = {
                    f.split('.')[0].split('[')[0]
                    for _, f, _, _ in string.Formatter().parse(tpl['text'])
                    if f
                }
                invalid = used - allowed
                assert not invalid, f"{key}/{tpl['key']} uses invalid placeholders: {invalid}"


class TestQuizSectionTemplates:
    def test_templates_use_registered_variables(self):
        from core.prompts.quiz_section_templates import describe_quiz_section_templates
        from core.prompts.variables import TOKEN_RE, prompt_variable_registry
        templates = describe_quiz_section_templates()
        keys = {t['key'] for t in templates}
        assert {'basic-attached', 'basic-standalone'} <= keys
        for tpl in templates:
            unknown = {
                m.group(1) for m in TOKEN_RE.finditer(tpl['text'])
                if prompt_variable_registry.get(m.group(1)) is None
            }
            assert not unknown, f"{tpl['key']} references unknown variables: {unknown}"

    def test_endpoint_accessible_to_course_staff(self, api_client, course_setup):
        from core.models import Quiz
        with factory.django.mute_signals(post_save):
            quiz = Quiz.objects.create(course=course_setup['course'], title='T',
                                       assignment=course_setup['assignment'])
        api_client.force_authenticate(user=course_setup['grader'])
        response = api_client.get(f'/quizzes/{quiz.id}/promptTemplates/')
        assert response.status_code == status.HTTP_200_OK
        keys = {t['key'] for t in response.data}
        assert 'retasking' in keys
        assert all('attachedOnly' in t and 'questionTypes' in t for t in response.data)

    def test_endpoint_forbidden_for_non_staff(self, api_client, course_setup):
        from core.models import Quiz
        with factory.django.mute_signals(post_save):
            quiz = Quiz.objects.create(course=course_setup['course'], title='T',
                                       assignment=course_setup['assignment'])
        api_client.force_authenticate(user=course_setup['student'])
        response = api_client.get(f'/quizzes/{quiz.id}/promptTemplates/')
        assert response.status_code == status.HTTP_403_FORBIDDEN
