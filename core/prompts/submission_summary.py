# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.prompts.registry import register_prompt


@register_prompt(
    'submission_summary',
    label='Submission Summary',
    description='Generate a summary overview of the student submission',
    allowed_placeholders=frozenset({
        'assignment_name', 'assignment_description',
        'test_results', 'rubric', 'description_comparison',
    }),
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
