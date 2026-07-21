# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.prompts.registry import Placeholder, PromptTemplate, register_prompt


@register_prompt(
    'comment_generation',
    label='Comment Generation',
    description='Inline code comments generated during grading',
    templates=[
        PromptTemplate(
            'concise',
            'Concise & encouraging',
            'Short, warm, actionable feedback — 1–2 sentences on the selected code.',
            """You are a supportive teaching assistant leaving an inline comment on a student's code.

Write one short comment (1–2 sentences) about the selected code:
- Name the specific issue and why it matters.
- Offer one concrete, encouraging next step.
- Do not rewrite the whole solution for the student.

Assignment: {assignment_name}
File: {file_name}
Selected code:
{selected_content}
""",
        ),
        PromptTemplate(
            'rubric-aligned',
            'Rubric-aligned',
            'Ties each comment to the selected rubric item so feedback maps to grading.',
            """You are grading a student's code and leaving an inline comment tied to a rubric item.

Ground your comment in the selected rubric item and explain how the highlighted code meets or
misses it. Be specific and constructive, and suggest a fix when appropriate. Keep it to 1–3 sentences.

Assignment: {assignment_name}
File: {file_name}
Rubric item: {rubric_context}
Selected code:
{selected_content}
""",
        ),
    ],
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
