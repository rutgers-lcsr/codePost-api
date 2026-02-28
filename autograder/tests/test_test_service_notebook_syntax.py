# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from typing import Any, cast

from django.test import SimpleTestCase

from autograder.services.TestService import TestService


class TestServiceNotebookSyntaxAdvisoryTests(SimpleTestCase):
    def test_detect_syntax_hint_from_notebook_cell_error_output(self):
        execution_result = {
            "stdout": "",
            "stderr": "",
            "error": None,
            "output_data": {
                "cells": [
                    {
                        "cell_type": "code",
                        "outputs": [
                            {
                                "output_type": "error",
                                "ename": "SyntaxError",
                                "evalue": "invalid syntax",
                                "traceback": ["Traceback ... SyntaxError: invalid syntax"],
                            }
                        ],
                    }
                ]
            },
        }

        hint = TestService._detect_syntax_hint(execution_result)

        self.assertIsNotNone(hint)
        if hint is None:
            self.fail("Expected syntax hint to be detected")
        self.assertIn("syntax", hint.lower())

    def test_verify_script_test_keeps_syntax_hint_advisory_for_is_error(self):
        execution_result = {
            "stdout": "",
            "stderr": "",
            "error": None,
            "output_data": {
                "cells": [
                    {
                        "cell_type": "code",
                        "outputs": [
                            {
                                "output_type": "error",
                                "ename": "SyntaxError",
                                "evalue": "invalid syntax",
                                "traceback": ["SyntaxError: invalid syntax"],
                            }
                        ],
                    }
                ]
            },
            "tests": [
                {
                    "name": "Test function exists",
                    "passed": False,
                    "score": 0,
                    "max_score": 1,
                    "status": "failed",
                    "error": "NameError: name 'foo' is not defined",
                }
            ],
        }

        verification = TestService.verify_script_test(cast(Any, None), execution_result)

        self.assertFalse(verification["passed"])
        self.assertFalse(verification["isError"])
        self.assertIn("syntax", verification["logs"].lower())

    def test_verify_script_test_ignores_syntax_hint_for_all_passing_tests(self):
        execution_result = {
            "stdout": "",
            "stderr": "",
            "error": None,
            "output_data": {
                "cells": [
                    {
                        "cell_type": "code",
                        "outputs": [
                            {
                                "output_type": "error",
                                "ename": "SyntaxError",
                                "evalue": "invalid syntax",
                                "traceback": ["SyntaxError: invalid syntax"],
                            }
                        ],
                    }
                ]
            },
            "tests": [
                {
                    "name": "Independent test",
                    "passed": True,
                    "score": 1,
                    "max_score": 1,
                    "status": "passed",
                    "error": "",
                }
            ],
        }

        verification = TestService.verify_script_test(cast(Any, None), execution_result)

        self.assertTrue(verification["passed"])
        self.assertFalse(verification["isError"])
        self.assertEqual(verification["score"], 1)
        self.assertEqual(verification["maxScore"], 1)
        self.assertNotIn("Detected a likely syntax/parse/compile error", verification["logs"])
        self.assertIn("Notebook syntax advisory", verification["logs"])
        self.assertIn("Full syntax details:", verification["logs"])
        self.assertIn("SyntaxError: invalid syntax", verification["logs"])
        self.assertIn("Notebook cell", verification["logs"])
        self.assertIn("Source:", verification["logs"])

    def test_verify_script_test_does_not_prepend_syntax_hint_for_unrelated_partial(self):
        execution_result = {
            "stdout": "",
            "stderr": "",
            "error": None,
            "output_data": {
                "cells": [
                    {
                        "cell_type": "code",
                        "outputs": [
                            {
                                "output_type": "error",
                                "ename": "SyntaxError",
                                "evalue": "invalid syntax",
                                "traceback": ["SyntaxError: invalid syntax"],
                            }
                        ],
                    }
                ]
            },
            "tests": [
                {
                    "name": "Always return partial",
                    "passed": False,
                    "score": 2,
                    "max_score": 10,
                    "status": "partial",
                    "error": None,
                    "message": "Partial Credit",
                }
            ],
        }

        verification = TestService.verify_script_test(cast(Any, None), execution_result)

        self.assertFalse(verification["passed"])
        self.assertFalse(verification["isError"])
        self.assertNotIn("Detected a likely syntax/parse/compile error", verification["logs"])
        self.assertIn("Notebook syntax advisory", verification["logs"])
        self.assertIn("Full syntax details:", verification["logs"])
        self.assertIn("SyntaxError: invalid syntax", verification["logs"])
        self.assertIn("Notebook cell", verification["logs"])
        self.assertIn("Source:", verification["logs"])
