# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Tests for detect_main_file heuristic in core.services.file_detection,
and integration tests verifying the task routes correctly based on detection.
"""
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.db.models.signals import post_save

import factory.django

from core.models import (
    Assignment, AssignmentFile, Course, Environment, Organization,
    Submission, SubmissionFile, TestCategory,
)
from core.services.file_detection import detect_main_file
from core.tests.factories import (
    AssignmentFactory,
    CourseFactory,
    OrganizationFactory,
    StudentFactory,
)


@factory.django.mute_signals(post_save)
def _make_assignment(course, name='Calculator', **kwargs):
    return Assignment.objects.create(
        course=course, name=name, points=20, **kwargs
    )


@factory.django.mute_signals(post_save)
def _make_submission(assignment):
    return Submission.objects.create(assignment=assignment)


@factory.django.mute_signals(post_save)
def _make_submission_file(submission, name, extension, data='', **kwargs):
    return SubmissionFile.objects.create(
        submission=submission, name=name, extension=extension, data=data, **kwargs
    )


@factory.django.mute_signals(post_save)
def _make_assignment_file(assignment, name, extension='.py', **kwargs):
    return AssignmentFile.objects.create(
        assignment=assignment, name=name, extension=extension, data='', **kwargs
    )


@factory.django.mute_signals(post_save)
def _make_environment(assignment, language='python-3.12'):
    return Environment.objects.create(assignment=assignment, language=language)


@factory.django.mute_signals(post_save)
def _make_test_category(assignment, name='Tests', targetFileName=None):
    return TestCategory.objects.create(
        assignment=assignment, name=name, targetFileName=targetFileName,
    )


class DetectMainFileTests(TestCase):
    """Unit tests for the detect_main_file scoring heuristic."""

    @factory.django.mute_signals(post_save)
    def setUp(self):
        self.org = Organization.objects.create(name='Test Org', shortname='testorg')
        self.course = Course.objects.create(
            name='cs101', period='s2026', organization=self.org,
        )

    def test_single_student_file_instant_pick(self):
        """When there's only one student file, return it immediately."""
        assignment = _make_assignment(self.course, name='HW1')
        _make_assignment_file(assignment, 'main.py', required=True)

        sub = _make_submission(assignment)
        f = _make_submission_file(sub, 'main.py', '.py', data='print("hello")')

        result = detect_main_file(sub)
        self.assertEqual(result, f)

    def test_no_student_files_returns_none(self):
        """When all files are hidden, return None."""
        assignment = _make_assignment(self.course, name='HW1')
        _make_assignment_file(assignment, 'helper.py', hidden=True)

        sub = _make_submission(assignment)
        _make_submission_file(sub, 'helper.py', '.py', data='# helper')

        result = detect_main_file(sub)
        self.assertIsNone(result)

    def test_assignment_name_match(self):
        """File whose stem matches the assignment name should be picked."""
        assignment = _make_assignment(self.course, name='Calculator')
        _make_assignment_file(assignment, 'calculator.py', required=True)
        _make_assignment_file(assignment, 'utils.py', required=True)

        sub = _make_submission(assignment)
        f_calc = _make_submission_file(sub, 'calculator.py', '.py', data='class Calculator: pass')
        _make_submission_file(sub, 'utils.py', '.py', data='def helper(): pass')

        result = detect_main_file(sub)
        self.assertEqual(result, f_calc)

    def test_python_entry_point_detection(self):
        """File with if __name__ == '__main__' should score highly."""
        assignment = _make_assignment(self.course, name='HW2')
        _make_environment(assignment, 'python-3.12')
        _make_assignment_file(assignment, 'app.py', required=True)
        _make_assignment_file(assignment, 'helper.py', required=True)

        sub = _make_submission(assignment)
        f_app = _make_submission_file(
            sub, 'app.py', '.py',
            data='def run():\n    pass\n\nif __name__ == "__main__":\n    run()\n',
        )
        _make_submission_file(sub, 'helper.py', '.py', data='def assist(): pass')

        result = detect_main_file(sub)
        self.assertEqual(result, f_app)

    def test_java_entry_point_detection(self):
        """File with public static void main should score highly in Java."""
        assignment = _make_assignment(self.course, name='HW3')
        _make_environment(assignment, 'java-17')
        _make_assignment_file(assignment, 'Main.java', '.java', required=True)
        _make_assignment_file(assignment, 'Helper.java', '.java', required=True)

        sub = _make_submission(assignment)
        f_main = _make_submission_file(
            sub, 'Main.java', '.java',
            data='public class Main {\n    public static void main(String[] args) {\n    }\n}',
        )
        _make_submission_file(
            sub, 'Helper.java', '.java',
            data='public class Helper {\n    public int help() { return 0; }\n}',
        )

        result = detect_main_file(sub)
        self.assertEqual(result, f_main)

    def test_test_category_target(self):
        """File targeted by a TestCategory should score highly."""
        assignment = _make_assignment(self.course, name='HW4')
        _make_assignment_file(assignment, 'solution.py', required=True)
        _make_assignment_file(assignment, 'lib.py', required=True)
        _make_test_category(assignment, name='Unit Tests', targetFileName='solution.py')

        sub = _make_submission(assignment)
        f_sol = _make_submission_file(sub, 'solution.py', '.py', data='def solve(): pass')
        _make_submission_file(sub, 'lib.py', '.py', data='def util(): pass')

        result = detect_main_file(sub)
        self.assertEqual(result, f_sol)

    def test_hidden_files_excluded_from_candidates(self):
        """Hidden assignment files should not be considered as main file."""
        assignment = _make_assignment(self.course, name='HW5')
        _make_assignment_file(assignment, 'solution.py', required=True)
        _make_assignment_file(assignment, 'test_runner.py', hidden=True)

        sub = _make_submission(assignment)
        f_sol = _make_submission_file(sub, 'solution.py', '.py', data='def solve(): pass')
        _make_submission_file(sub, 'test_runner.py', '.py', data='# test runner code\nif __name__ == "__main__":\n    run_tests()')

        result = detect_main_file(sub)
        self.assertEqual(result, f_sol)

    def test_ambiguous_files_returns_none(self):
        """When multiple files have equal low scores, return None (fallback)."""
        assignment = _make_assignment(self.course, name='HW6')
        # Two files, neither required, no entry points, no test targets, no name match
        sub = _make_submission(assignment)
        _make_submission_file(sub, 'a.py', '.py', data='x = 1')
        _make_submission_file(sub, 'b.py', '.py', data='y = 2')

        result = detect_main_file(sub)
        self.assertIsNone(result)

    def test_main_filename_pattern(self):
        """Well-known 'main' filename should score highly."""
        assignment = _make_assignment(self.course, name='HW7')
        _make_environment(assignment, 'python-3.12')
        _make_assignment_file(assignment, 'main.py', required=True)
        _make_assignment_file(assignment, 'data.py', required=True)

        sub = _make_submission(assignment)
        f_main = _make_submission_file(sub, 'main.py', '.py', data='# entry point')
        _make_submission_file(sub, 'data.py', '.py', data='DATA = [1,2,3]')

        result = detect_main_file(sub)
        self.assertEqual(result, f_main)

    def test_description_mention(self):
        """File mentioned in the AI description should get a score boost."""
        assignment = _make_assignment(self.course, name='HW8')
        assignment.ai_description = 'Students should implement their solution in solver.py'
        assignment.save()
        _make_assignment_file(assignment, 'solver.py', required=True)
        _make_assignment_file(assignment, 'config.py', required=True)

        sub = _make_submission(assignment)
        f_solver = _make_submission_file(sub, 'solver.py', '.py', data='def solve(): pass')
        _make_submission_file(sub, 'config.py', '.py', data='SETTING = True')

        result = detect_main_file(sub)
        self.assertEqual(result, f_solver)

    def test_largest_file_tiebreaker(self):
        """When scores are tied, largest file should win via tiebreaker."""
        assignment = _make_assignment(self.course, name='HW9')
        _make_assignment_file(assignment, 'file_a.py', required=True)
        _make_assignment_file(assignment, 'file_b.py', required=True)

        sub = _make_submission(assignment)
        _make_submission_file(sub, 'file_a.py', '.py', data='x = 1')
        f_b = _make_submission_file(sub, 'file_b.py', '.py', data='y = 2\n' * 100)

        result = detect_main_file(sub)
        # Both have _SCORE_REQUIRED_FILE (3), but file_b gets +1 for largest → wins
        self.assertEqual(result, f_b)

    def test_c_entry_point_detection(self):
        """File with int main( should score highly in C/C++."""
        assignment = _make_assignment(self.course, name='HW10')
        _make_environment(assignment, 'c/c++')
        _make_assignment_file(assignment, 'main.c', '.c', required=True)
        _make_assignment_file(assignment, 'utils.c', '.c', required=True)

        sub = _make_submission(assignment)
        f_main = _make_submission_file(
            sub, 'main.c', '.c',
            data='#include <stdio.h>\nint main(int argc, char *argv[]) {\n    return 0;\n}',
        )
        _make_submission_file(sub, 'utils.c', '.c', data='int add(int a, int b) { return a + b; }')

        result = detect_main_file(sub)
        self.assertEqual(result, f_main)

    def test_no_environment_still_works(self):
        """Detection should work even if no Environment is configured."""
        assignment = _make_assignment(self.course, name='Calculator')
        # No environment created
        _make_assignment_file(assignment, 'calculator.py', required=True)
        _make_assignment_file(assignment, 'helpers.py', required=True)

        sub = _make_submission(assignment)
        f_calc = _make_submission_file(sub, 'calculator.py', '.py', data='class Calc: pass')
        _make_submission_file(sub, 'helpers.py', '.py', data='def h(): pass')

        result = detect_main_file(sub)
        # Should still detect via assignment name match
        self.assertEqual(result, f_calc)


class TaskRoutingTests(TestCase):
    """Integration tests verifying generate_ai_grading_assistance routes
    to the correct generation method based on main file detection."""

    @factory.django.mute_signals(post_save)
    def setUp(self):
        self.org = Organization.objects.create(
            name='Route Org', shortname='routeorg',
            ai_provider='gemini', ai_api_key='test-key',
        )
        self.course = Course.objects.create(
            name='cs201', period='s2026', organization=self.org,
        )

    @factory.django.mute_signals(post_save)
    def _make_submission_with_files(self, assignment_name, files_spec):
        """Helper to create an assignment + submission with specified files.

        files_spec: list of (name, ext, data, kwargs_dict) tuples
        """
        assignment = Assignment.objects.create(
            course=self.course, name=assignment_name, points=20,
        )
        sub = Submission.objects.create(assignment=assignment)
        file_objs = []
        for name, ext, data, kwargs in files_spec:
            af = AssignmentFile.objects.create(
                assignment=assignment, name=name, extension=ext, data='', **kwargs,
            )
            sf = SubmissionFile.objects.create(
                submission=sub, name=name, extension=ext, data=data,
            )
            file_objs.append(sf)
        return sub, file_objs

    @patch('core.services.ai_service.AIService.generate_submission_summary')
    @patch('core.services.ai_service.AIService.generate_file_suggestions')
    @patch('core.services.ai_service.AIService.generate_suggested_comments')
    @patch('core.services.ai_service.AIService.is_configured', new_callable=lambda: property(lambda self: True))
    @patch('core.services.ai_service.AIService.is_globally_disabled', new_callable=lambda: property(lambda self: False))
    def test_routes_to_file_suggestions_when_main_detected(
        self, _mock_disabled, _mock_configured,
        mock_gen_all, mock_gen_file, mock_gen_summary,
    ):
        """When detect_main_file returns a file, task should call generate_file_suggestions."""
        from core.services.ai_service import GenerationResult

        mock_gen_file.return_value = [GenerationResult(text='[]', success=True)]
        mock_gen_summary.return_value = GenerationResult(text='Summary', success=True)

        # Single required file → instant pick by detect_main_file
        sub, files = self._make_submission_with_files('SingleFile', [
            ('main.py', '.py', 'print("hi")', {'required': True}),
        ])

        from core.tasks import generate_ai_grading_assistance
        generate_ai_grading_assistance(sub.id)

        # Should call generate_file_suggestions (not generate_suggested_comments)
        mock_gen_file.assert_called_once()
        mock_gen_all.assert_not_called()

        # Summary should be called with target_file kwarg
        mock_gen_summary.assert_called_once()
        _, kwargs = mock_gen_summary.call_args
        self.assertIsNotNone(kwargs.get('target_file'))

    @patch('core.services.ai_service.AIService.generate_submission_summary')
    @patch('core.services.ai_service.AIService.generate_file_suggestions')
    @patch('core.services.ai_service.AIService.generate_suggested_comments')
    @patch('core.services.ai_service.AIService.is_configured', new_callable=lambda: property(lambda self: True))
    @patch('core.services.ai_service.AIService.is_globally_disabled', new_callable=lambda: property(lambda self: False))
    def test_routes_to_all_files_when_no_main_detected(
        self, _mock_disabled, _mock_configured,
        mock_gen_all, mock_gen_file, mock_gen_summary,
    ):
        """When detect_main_file returns None, task should call generate_suggested_comments."""
        from core.services.ai_service import GenerationResult

        mock_gen_all.return_value = [GenerationResult(text='[]', success=True)]
        mock_gen_summary.return_value = GenerationResult(text='Summary', success=True)

        # Two ambiguous files, no signals → detect_main_file returns None
        sub, files = self._make_submission_with_files('Ambiguous', [
            ('a.py', '.py', 'x = 1', {}),
            ('b.py', '.py', 'y = 2', {}),
        ])

        from core.tasks import generate_ai_grading_assistance
        generate_ai_grading_assistance(sub.id)

        # Should call generate_suggested_comments (not generate_file_suggestions)
        mock_gen_all.assert_called_once()
        mock_gen_file.assert_not_called()

        # Summary should be called with target_file=None
        mock_gen_summary.assert_called_once()
        _, kwargs = mock_gen_summary.call_args
        self.assertIsNone(kwargs.get('target_file'))
