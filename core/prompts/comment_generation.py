# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.prompts.registry import register_prompt


@register_prompt(
    'comment_generation',
    label='Comment Generation',
    description='Inline code comments generated during grading',
    allowed_placeholders=frozenset({
        'assignment_name', 'file_name', 'file_content',
        'selected_content', 'rubric_context', 'grader_draft', 'all_files',
    }),
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
