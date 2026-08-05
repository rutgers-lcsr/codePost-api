# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.prompts.registry import register_prompt


@register_prompt(
    'quiz_generation',
    label='Quiz Question Suggestions',
    description='Generate suggested quiz questions from an assignment and course material',
    allowed_placeholders=frozenset({
        'assignment_name', 'explanation', 'template_files', 'test_cases', 'rubric',
        'course_materials', 'language', 'num_questions', 'question_types',
        'existing_question', 'instructions',
    }),
)
def DEFAULT_TEMPLATE():
    return """You are helping an instructor author quiz questions for a programming course.
Based on the provided materials, suggest high-quality quiz questions that assess whether students
understand the concepts behind this assignment.

Guidelines:
- Write clear, unambiguous questions at an appropriate difficulty for the material.
- Prefer questions that test understanding and application, not trivia.
- Allowed question types: {question_types}. Only use these types.
- Assign a reasonable integer `points` value to each question.
- Keep the `text` stem concise. Put supporting context in the optional `description` — it is shown
  to the student beneath the stem and rendered as Markdown, so use Markdown for highlighting:
  fenced code blocks for code excerpts or sample input/output, plus bold, inline code, and lists.

CHOICES ARE REQUIRED for these types — never return them with an empty `choices` array:
- `multiple_choice`: 3-5 plausible choices; exactly ONE has "is_correct": true.
- `multiple_answers`: 3-5 choices; one OR MORE have "is_correct": true.
- `true_false`: exactly two choices, {{"text": "True", ...}} and {{"text": "False", ...}}, one correct.
- `short_answer` / `numerical`: each acceptable answer is a choice with "is_correct": true.
ONLY these types have no choices (use an empty array): `essay`, `code`.
For `code` questions, write the prompt in the language: {language}; you may include `starter_code`
and a `reference_solution` in that language.

REFRESH MODE (only when an existing question is provided below): produce exactly ONE improved variant of
that question — keep its intent and type unless the instructions say otherwise, fix any issues, and apply
the instructor's instructions. Otherwise, generate {num_questions} new questions.

Instructor instructions (may be empty): {instructions}

{existing_question}

Output format: respond with ONLY a JSON array (no markdown, no prose). Each element is an object:
{{
  "type": "<one of {question_types}>",
  "text": "<the question stem>",
  "description": "<optional Markdown shown to the student beneath the stem>",
  "points": <integer>,
  "choices": [{{"text": "<choice text>", "is_correct": <true|false>, "feedback": "<optional>"}}],
  "starter_code": "<optional, code questions only>",
  "reference_solution": "<optional, code questions only>"
}}

Worked example (a multiple_choice question MUST look like this — note the populated choices):
[
  {{
    "type": "multiple_choice",
    "text": "Which call creates an empty Python dictionary?",
    "points": 2,
    "choices": [
      {{"text": "dict()", "is_correct": true}},
      {{"text": "[]", "is_correct": false}},
      {{"text": "set()", "is_correct": false}},
      {{"text": "()", "is_correct": false}}
    ]
  }}
]

--- Assignment context ---
Assignment Name: {assignment_name}
Student-Facing Instructions: {explanation}

{template_files}

{test_cases}

{rubric}

{course_materials}
"""
