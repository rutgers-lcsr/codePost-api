# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from core.prompts.registry import register_prompt


@register_prompt(
    'personalized_quiz_generation',
    label='Personalized Quiz Questions',
    description="Generate per-student quiz questions from an assignment and the student's own submission",
    allowed_placeholders=frozenset({
        'instructor_prompt', 'assignment_name', 'num_questions', 'question_types', 'language',
    }),
)
def DEFAULT_TEMPLATE():
    return """You are generating quiz questions personalized to one student's submission for a
programming course assignment ({assignment_name}). The instructor will review your questions before
the student sees them.

Guidelines:
- Generate exactly {num_questions} questions.
- Base the questions on the student's OWN code and work: reference their actual identifiers,
  structure, and decisions so the questions verify the student understands what they submitted.
- Write clear, unambiguous questions. Prefer understanding and application over trivia.
- Never mention how the questions were produced, and never address the student directly about
  their grade or feedback.
- Allowed question types: {question_types}. Only use these types.
- Assign a reasonable integer `points` value to each question.

CHOICES ARE REQUIRED for these types — never return them with an empty `choices` array:
- `multiple_choice`: 3-5 plausible choices; exactly ONE has "is_correct": true.
- `multiple_answers`: 3-5 choices; one OR MORE have "is_correct": true.
- `true_false`: exactly two choices, {{"text": "True", ...}} and {{"text": "False", ...}}, one correct.
- `short_answer` / `numerical`: each acceptable answer is a choice with "is_correct": true.
ONLY these types have no choices (use an empty array): `essay`, `code`.
For `code` questions, write the prompt in the language: {language}; you may include `starter_code`.

--- Instructor's instructions for this quiz section (already includes any referenced material) ---
{instructor_prompt}
--- End of instructor's instructions ---

Output format: respond with ONLY a JSON array (no markdown, no prose). Each element is an object:
{{
  "type": "<one of {question_types}>",
  "text": "<the question stem>",
  "points": <integer>,
  "choices": [{{"text": "<choice text>", "is_correct": <true|false>, "feedback": "<optional>"}}],
  "starter_code": "<optional, code questions only>"
}}

Worked example (a multiple_choice question MUST look like this — note the populated choices):
[
  {{
    "type": "multiple_choice",
    "text": "In your solution, what does the helper function `merge_runs` return?",
    "points": 2,
    "choices": [
      {{"text": "A new sorted list", "is_correct": true}},
      {{"text": "The input list, mutated in place", "is_correct": false}},
      {{"text": "An iterator over pairs", "is_correct": false}},
      {{"text": "None", "is_correct": false}}
    ]
  }}
]
"""
