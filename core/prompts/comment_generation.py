# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.prompts.registry import Placeholder, register_prompt


@register_prompt(
    'comment_generation',
    label='Comment Generation',
    description='Inline code comments generated during grading',
    placeholders=[
        # Variables marked (auto) are appended to the User Prompt automatically if omitted
        # from the System Prompt; variables marked (manual) must be included explicitly.
        Placeholder('assignment_name', 'Name of the assignment',
                    'The name of the assignment being graded.'),
        Placeholder('file_name', 'Name of the file being reviewed',
                    'The name of the file the comment is on.'),
        Placeholder('rubric_context', 'Selected rubric item details (auto)',
                    'Details of the rubric item the grader selected.'),
        Placeholder('selected_content', 'The specific code block selected (auto)',
                    'The exact code the grader highlighted.'),
        Placeholder('grader_draft', "Grader's current draft text (auto)",
                    'The comment text the grader has drafted so far.'),
        Placeholder('file_content', 'Full content of the current file (auto)',
                    'The entire contents of the file being reviewed.'),
        Placeholder('all_files', 'Content of all files in the submission (manual)',
                    "Every file in the student's submission. Must be included explicitly."),
    ],
)
def DEFAULT_TEMPLATE():
    return """You are an AI assistant helping grade student code submissions.
Your task is to generate clear, constructive feedback for students.

Guidelines:
- Be specific about what the issue is
- Explain why it matters
- Suggest how to fix it when appropriate
- Be encouraging but honest
- Keep comments concise (1-3 sentences)

Context:
- Assignment: {assignment_name}
- File: {file_name}
- File Content:
{file_content}
"""
