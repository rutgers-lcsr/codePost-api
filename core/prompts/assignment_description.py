# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.prompts.registry import register_prompt


@register_prompt(
    'assignment_description',
    label='Assignment Description',
    description='Generate an assignment description from uploaded starter code',
    allowed_placeholders=frozenset({
        'assignment_name', 'explanation', 'template_files',
        'test_cases', 'rubric', 'submission_samples',
    }),
)
def DEFAULT_TEMPLATE():
    return """You are analyzing a programming assignment.
Based on the provided materials (template code, test definitions, rubric, student-facing instructions,
and sample student submissions), generate a clear, concise description of what this assignment asks
students to do.

Include:
- The main objective and learning goals
- Key requirements and constraints
- What a correct solution should accomplish
- Important implementation details students need to handle
- **Main submission file**: Identify which file is the primary/main file that students are expected \
to implement their solution in (e.g. "The main submission file is `calculator.py`."). Look at which \
file contains the core logic, is targeted by tests, or is the entry point. Use the exact filename \
(e.g. `calculator.py`, not just `calculator`). If multiple files are equally important, list them all.

This description will be used as AI context to help generate better feedback for student submissions. Do not reply to me directly — just generate the description text.
Keep it factual and specific — avoid generic statements.

Assignment Name: {assignment_name}
Student-Facing Instructions: {explanation}

{template_files}

{test_cases}

{rubric}

{submission_samples}
"""
