from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from autograder.services.TestParsingService import TestParsingService
from core.services.ai_service import AIService


class TestParsingServiceAlignmentTests(SimpleTestCase):
    def _parse(self, script: str, language: str):
        category = SimpleNamespace(testScript=script)
        return TestParsingService.parse_script(category, language=language)

    def test_ai_examples_parse_for_supported_languages(self):
        expected_by_language = {
            "python": ["Test Name", "Test Partial", "Test Explanation"],
            "java": ["Test Name", "Test Partial", "Test Explanation"],
            "javascript": ["Test Name", "Test Partial", "Test Explanation"],
            "node": ["Test Name", "Test Partial", "Test Explanation"],
            "cpp": ["TestName", "TestPartial", "TestExplanation"],
            "c": ["TestName", "TestPartial", "TestExplanation"],
            "r": ["Test Name", "Test Partial", "Test Explanation"],
            "php": ["Test Name", "Test Partial", "Test Explanation"],
            "ruby": ["Test Name", "Test Partial", "Test Explanation"],
        }

        for language, expected_names in expected_by_language.items():
            script = AIService.LANGUAGE_EXAMPLES[language]
            parsed = self._parse(script, language)

            self.assertGreaterEqual(
                len(parsed),
                3,
                msg=f"Expected at least 3 parsed tests for language '{language}', got {len(parsed)}",
            )

            parsed_names = [test["name"] for test in parsed]
            self.assertEqual(
                parsed_names[:3],
                expected_names,
                msg=f"Parsed names mismatch for language '{language}'",
            )

            for test in parsed[:3]:
                self.assertIn("points", test)
                self.assertGreater(test["points"], 0)

    def test_java_autodetection_accepts_non_void_test_methods(self):
        category = SimpleNamespace(testScript=AIService.LANGUAGE_EXAMPLES["java"])
        parsed = TestParsingService.parse_script(category)

        self.assertGreaterEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "Test Name")

    def test_update_test_cases_uses_assignment_environment_language(self):
        category = SimpleNamespace(
            testScript=AIService.LANGUAGE_EXAMPLES["java"],
            assignment=SimpleNamespace(environment=SimpleNamespace(language="java-17")),
            testCases=SimpleNamespace(all=lambda: []),
            pk=123,
        )

        with patch.object(TestParsingService, "parse_script", return_value=[]) as parse_mock, \
             patch("autograder.services.TestParsingService.TestCategory.objects.filter") as filter_mock:
            filter_mock.return_value.update = MagicMock()

            TestParsingService.update_test_cases(category)

        parse_mock.assert_called_once_with(category, language="java-17")
