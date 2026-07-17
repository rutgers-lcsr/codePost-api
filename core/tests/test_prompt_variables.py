# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for the prompt variable framework (core/prompts/variables.py): regex
substitution semantics, strict save-time validation, and the autocomplete payload."""
import factory
import pytest
from django.db.models.signals import post_save

from core.prompts.variables import (
    VariableContext, describe_available_variables, substitute_variables, validate_template,
)


@pytest.fixture
def assignment_setup(db):
    from core.tests.factories import CourseFactory, AssignmentFileFactory

    with factory.django.mute_signals(post_save):
        course = CourseFactory(name="cos126", period="s2026", organization__name="Princeton")
        assignment = course.assignments.first()
        AssignmentFileFactory(assignment=assignment, name='starter.py', data='print("hi")')
        AssignmentFileFactory(assignment=assignment, name='secret.py', data='key', hidden=True)
    return {'course': course, 'assignment': assignment}


class TestSubstitution:
    def test_literal_braces_pass_through(self):
        ctx = VariableContext(course=None)
        text, used = substitute_variables('Return JSON like {"a": 1} or {}.', ctx)
        assert text == 'Return JSON like {"a": 1} or {}.'
        assert used == set()

    def test_unknown_variable_passes_through(self):
        ctx = VariableContext(course=None)
        text, used = substitute_variables('keep {not_a_real_variable} as-is', ctx)
        assert text == 'keep {not_a_real_variable} as-is'
        assert used == set()

    def test_unresolvable_variable_becomes_marker(self):
        # assignment_name is registered but there's no assignment in context.
        ctx = VariableContext(course=None)
        text, used = substitute_variables('for {assignment_name}!', ctx)
        assert text == 'for (unavailable: {assignment_name})!'
        assert used == {'assignment_name'}

    def test_static_and_parameterized_resolution(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        text, used = substitute_variables(
            'A: {assignment_name}\n{assignment_file:starter.py}', ctx)
        assert 'A: ' + assignment_setup['assignment'].name in text
        assert 'print("hi")' in text
        assert used == {'assignment_name', 'assignment_file'}

    def test_missing_file_argument_becomes_marker(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        text, _ = substitute_variables('{assignment_file:nope.py}', ctx)
        assert text == '(unavailable: {assignment_file:nope.py})'

    def test_hidden_files_never_resolve(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        text, _ = substitute_variables('{assignment_file:secret.py}', ctx)
        assert 'key' not in text
        assert '(unavailable' in text

    def test_argument_on_static_variable_becomes_marker(self):
        ctx = VariableContext(course=None)
        text, _ = substitute_variables('{num_questions:5}', ctx)
        assert text == '(unavailable: {num_questions:5})'

    def test_section_variables(self, assignment_setup):
        from core.models import Quiz, QuizGeneratedSection
        quiz = Quiz.objects.create(course=assignment_setup['course'], title='Q',
                                   assignment=assignment_setup['assignment'])
        section = QuizGeneratedSection.objects.create(
            quiz=quiz, systemPrompt='x', numQuestions=4, questionTypes=['essay'])
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'], section=section)
        text, _ = substitute_variables('{num_questions} of {question_types}', ctx)
        assert text == '4 of essay'


class TestValidation:
    def test_valid_template(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        errors = validate_template(
            'Ask about {assignment_file:starter.py} and {submission_files}. JSON: {"a": 1}', ctx)
        assert errors == []

    def test_unknown_variable_is_error(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        errors = validate_template('{bogus_variable}', ctx)
        assert errors == ["Unknown variable '{bogus_variable}'."]

    def test_missing_argument_is_error(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        errors = validate_template('{assignment_file}', ctx)
        assert len(errors) == 1 and 'needs an argument' in errors[0]

    def test_argument_on_static_variable_is_error(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        errors = validate_template('{assignment_name:foo}', ctx)
        assert len(errors) == 1 and 'does not take an argument' in errors[0]

    def test_unknown_assignment_file_is_error(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        errors = validate_template('{assignment_file:missing.py}', ctx)
        assert len(errors) == 1 and 'no file named' in errors[0]

    def test_assignment_variable_without_assignment_is_error(self):
        ctx = VariableContext(course=None)
        errors = validate_template('{submission_files}', ctx)
        assert len(errors) == 1 and 'attached to an assignment' in errors[0]

    def test_duplicate_tokens_error_once(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        errors = validate_template('{bogus} then {bogus}', ctx)
        assert len(errors) == 1


class TestDescribeAvailableVariables:
    def test_expands_assignment_files(self, assignment_setup):
        ctx = VariableContext(course=assignment_setup['course'],
                              assignment=assignment_setup['assignment'])
        entries = describe_available_variables(ctx)
        tokens = {e['token'] for e in entries}
        assert '{assignment_name}' in tokens
        assert '{submission_files}' in tokens
        assert '{assignment_file:starter.py}' in tokens
        assert '{submission_file:starter.py}' in tokens
        # Hidden files are never offered.
        assert '{assignment_file:secret.py}' not in tokens
        kinds = {e['token']: e['kind'] for e in entries}
        assert kinds['{assignment_file:starter.py}'] == 'file'
        assert kinds['{assignment_name}'] == 'static'

    def test_without_assignment_only_section_variables(self):
        entries = describe_available_variables(VariableContext(course=None))
        tokens = {e['token'] for e in entries}
        assert tokens == {'{num_questions}', '{question_types}'}


class TestTemplateRequirements:
    def test_classification_drives_generation_timing(self):
        from core.prompts.variables import template_requirements, template_requires_submission
        # Section-only / plain prompts need nothing → eager, standalone-capable.
        assert template_requirements('Ask {num_questions} things about recursion.') == set()
        assert template_requires_submission('Plain prompt, no variables.') is False
        # Assignment data needs attachment but not a submission.
        assert template_requirements('Use {assignment_name} and {assignment_files}.') == {'assignment'}
        assert template_requires_submission('{assignment_file:main.py}') is False
        # Per-student submission data needs both.
        assert template_requirements('Read {submission_files}.') == {'assignment', 'submission'}
        assert template_requires_submission('{submission_file:main.py}') is True
        assert template_requires_submission('{submission_test_results}') is True
