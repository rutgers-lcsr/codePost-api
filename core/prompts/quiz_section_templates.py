# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Starter prompt templates for AI-generated quiz sections.

These are the quiz-side counterpart to the ``PromptRegistry`` templates: the quiz section
editor (``QuizGeneratedSection.systemPrompt``) uses the richer instructor-facing variable
system in ``core/prompts/variables.py`` (regex ``{submission_files}`` etc.), NOT the
``str.format`` prompt registry — so its templates live here and are served by the quiz
``promptTemplates`` action rather than ``/promptTypes/``.

Every ``{variable}`` used below must be registered in ``core/prompts/variables.py`` (validated
server-side when a section is saved). ``<<SAMPLE_ROWS>>`` is a deliberately non-``{}`` client
token substituted with the instructor's chosen sample size before the prompt is applied.
"""
from dataclasses import dataclass

SAMPLE_ROWS_TOKEN = '<<SAMPLE_ROWS>>'


@dataclass(frozen=True)
class QuizSectionTemplate:
    key: str
    label: str
    description: str
    # True when the template references the student's submission, so it only makes sense on a
    # quiz attached to an assignment.
    attached_only: bool
    question_types: tuple[str, ...]
    text: str


QUIZ_SECTION_TEMPLATES: list[QuizSectionTemplate] = [
    QuizSectionTemplate(
        'basic-attached',
        'Basic — comprehension check',
        "Checks the student understands the code they submitted. The default for quizzes "
        "attached to an assignment.",
        attached_only=True,
        question_types=(),
        text="""Ask questions that check this student understands the code they submitted — its structure, its behavior, and the decisions they made.

Their submission:
{submission_files}

Their autograder results:
{submission_test_results}""",
    ),
    QuizSectionTemplate(
        'basic-standalone',
        'Basic — topic check (standalone)',
        "Checks the student understands the quiz's topics. The default for standalone quizzes "
        "with no attached assignment.",
        attached_only=False,
        question_types=(),
        text="""Ask {num_questions} questions that check the student understands the topics this quiz covers. Vary the questions between students.""",
    ),
    QuizSectionTemplate(
        'retasking',
        'Retasking — rewrite your own code',
        "Quotes a piece of the student's own code and asks them to adapt it to different inputs "
        "or parameters — proves they understand it well enough to reuse it, not just that it runs.",
        attached_only=True,
        question_types=('code',),
        text="""Ask questions that "retask" this student's own submitted code: quote an exact expression, function, or short block from their submission (as a fenced code block in the question's description), then ask them to rewrite it applied to different variables, parameters, or inputs — using the same underlying approach they used.

Each question must:
- Quote the student's actual code, not a generic example.
- Ask for a rewritten version applied to something different (a different column, group, parameter, or input) — not a verbatim repeat.
- Be answerable only by someone who understands what their original code does, not by someone who can just copy-paste it.

Their submission:
{submission_files}""",
    ),
    QuizSectionTemplate(
        'manual-evaluation',
        'Manual evaluation — hand-compute a small example',
        "Gives the student a tiny sample of data and asks them to hand-compute, step by step, "
        "what their own code would return on it — confirms they understand the logic.",
        attached_only=True,
        question_types=('numerical', 'short_answer'),
        text="""Ask questions that test whether this student can hand-compute the result of their own code on a small example, without running it.

For each question:
- Quote a specific expression, function, or line from their submission (in the description).
- Make up a tiny example — about <<SAMPLE_ROWS>> rows/values — small enough to compute by hand, and show it in the description as a table or short list.
- Ask what their code would return on that exact example.
- Use question type numerical or short_answer, with the correct computed result as the accepted answer.

Their submission:
{submission_files}""",
    ),
    QuizSectionTemplate(
        'understanding-check',
        'Understanding check — retasking + manual evaluation',
        "The combined approach: some questions ask the student to retask their own code to new "
        "inputs, others ask them to hand-compute a small example.",
        attached_only=True,
        question_types=('code', 'numerical', 'short_answer', 'essay'),
        text="""Ask questions that check whether this student truly understands the code they submitted (as opposed to having it written for them). Use a mix of two styles:

1. Retasking: quote an exact expression or block from their submission (as a fenced code block in the description) and ask them to rewrite it applied to different variables, parameters, or inputs, using the same approach.
2. Manual evaluation: quote a specific expression from their submission, make up a tiny example (about <<SAMPLE_ROWS>> rows/values, shown in the description as a table or short list), and ask what their code would return on it, computed by hand.

Their submission:
{submission_files}""",
    ),
    QuizSectionTemplate(
        'explain-your-code',
        'Explain your code',
        "Quotes a block of the student's own code and asks them to explain, in their own words, "
        "what it does and why — purely conceptual. Catches code a student can't describe.",
        attached_only=True,
        question_types=('essay',),
        text="""Ask essay questions that quote a specific block of this student's submitted code (as a fenced code block in the description) and ask them to explain, in their own words, what it does and why they wrote it that way. No rewriting or computation required — this checks conceptual understanding, not code-writing ability.

Their submission:
{submission_files}""",
    ),
]


def describe_quiz_section_templates() -> list[dict]:
    """The template-picker payload for the quiz section editor. Returns all templates with an
    ``attachedOnly`` flag; the frontend shows the appropriate subset for the quiz."""
    return [
        {
            'key': t.key,
            'label': t.label,
            'description': t.description,
            'attachedOnly': t.attached_only,
            'questionTypes': list(t.question_types),
            'text': t.text,
        }
        for t in QUIZ_SECTION_TEMPLATES
    ]
