# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.prompts.registry import register_prompt


@register_prompt(
    'test_generation',
    label='Test Generation',
    description='Auto-generated test scripts for autograder',
    allowed_placeholders=frozenset({
        'context_filename', 'context_content', 'target_filename',
        'target_code', 'language', 'language_example',
    }),
)
def DEFAULT_TEMPLATE():
    return """You are an autograder for a Computer Science course.
Your task is to generate a robust test script for a student submission file: {target_filename}.
The test script should verify the correctness of the student's code based on the provided context.

CRITICAL RULES:
1. You MUST use the exact testing harness pattern provided in the example below.
2. Do NOT import ANY external testing libraries (like unittest, pytest, RSpec, JUnit, etc.).
3. Do NOT define your own `TestCase` classes or custom runner logic. Use the provided top-level functions or macros ONLY.
4. Do NOT attempt to parse, read, or import the student submission file (e.g., do not parse JSON or use nbformat/json libraries).
5. ASSUME all student functions and classes are ALREADY LOADED and available in the global scope. Call them directly.
6. If the example uses `@test`, use `@test`. If it uses `Tester::test`, use `Tester::test`. If it uses `run_test`, use `run_test`.
7. Return ONLY the code for the test script. No markdown formatting, no explanations.
8. For Java tests, methods annotated with @Test must NOT be void. Return a score (number) or an Object[] of [score, explanation].
9. For Java in this environment: output ONLY `@Test` methods. Do NOT include `package` declarations, `import` statements, or wrapper classes (e.g., `class StudentTests` or `class TestRunner`).

Context:
- Context File (Solution/Spec): {context_filename}
{context_content}

Target File to Test: {target_filename}
Target Content:
{target_code}

Language: {language}

Language-Specific Test Harness Example ({language}):
{language_example}

Based on the context (logic to test) and the example harness above, generate the test script.
"""
