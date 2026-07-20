# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.prompts.registry import Placeholder, register_prompt


@register_prompt(
    'submission_summary',
    label='Submission Summary',
    description='Generate a summary overview of the student submission',
    placeholders=[
        Placeholder('assignment_name', 'Name of the assignment',
                    'The name of the assignment.'),
        Placeholder('assignment_description', 'Assignment context description',
                    "The assignment's AI context description (from AI Grading Assistance)."),
        Placeholder('test_results', 'Autograder test results',
                    "Overview of the student's autograder test results."),
        Placeholder('rubric', 'Grading rubric',
                    "The assignment's grading rubric."),
        Placeholder('description_comparison', 'Requirements-comparison instruction',
                    'A sentence instructing the AI to compare the submission to the '
                    'assignment requirements (only when a description exists).'),
    ],
)
def DEFAULT_TEMPLATE():
    return """You are an assistant helping graders understand student submissions.
Generate a concise summary that helps the grader quickly orient themselves before reviewing.

Include:
- What the student implemented — mention specific class names, functions, and design patterns used
- Key strengths worth noting
- Key issues or concerns requiring grader attention
- Test results overview (which passed/failed and why, if available)
- **Grading priority**: which files or areas should the grader review most carefully, and why
{description_comparison}

Keep the summary to 5-10 bullet points. Use markdown formatting. Just respond with the summary text — do not reply to me directly.

Assignment: {assignment_name}
{assignment_description}

{rubric}
"""
