# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Quiz read tools."""
from __future__ import annotations

from core.agent import shaping
from core.agent.registry import SCOPE_READ, tool
from core.agent.tools._common import course_header
from core.permissions.capabilities import Capability


@tool(
    name='codepost_get_quiz_status',
    title='Quiz status',
    description=(
        "Quizzes in the course and how they're going. view='list' shows every "
        "quiz with publication state; view='results' shows per-student official "
        "scores for one quiz (requires quizId); view='needsGrading' shows which "
        'quizzes have responses waiting on manual grading.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'view': {'enum': ['list', 'results', 'needsGrading'], 'default': 'list'},
            'quizId': {'type': 'integer',
                       'description': "Required for view='results'."},
            'limit': {'type': 'integer', 'default': 50, 'maximum': 200},
            'cursor': {'type': 'string'},
        },
        'additionalProperties': False,
    },
    capability=Capability.GRADE_QUIZ,
    min_scope=SCOPE_READ,
    read_only=True,
)
def get_quiz_status(ctx, view: str = 'list', quizId=None, limit: int = 50,
                    cursor: str = ''):
    from core.agent import errors
    from core.views.course import CourseViewSet
    from core.views.quiz import QuizViewSet

    if view == 'results':
        if quizId is None:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET', "view='results' needs a quizId.",
                remedy="Call codepost_get_quiz_status(view='list') to find it.",
                retryable=True)
        rows = ctx.dispatch.require(
            QuizViewSet, {'get': 'results'},
            method='GET', path=f'/quizzes/{quizId}/results/', pk=quizId,
            what=f'reading results for quiz {quizId}')
        offset = shaping.decode_cursor(cursor).get('offset', 0)
        window, meta = shaping.paginate(
            rows or [], limit=shaping.clamp_limit(limit), offset=offset,
            cursor_payload={'view': view, 'quizId': quizId})
        needs = sum(1 for r in (rows or []) if r.get('needsGrading'))
        return shaping.enforce_budget(shaping.envelope(
            {'course': course_header(ctx.course), 'quizId': quizId,
             'summary': {'students': len(rows or []), 'needsGrading': needs},
             'results': window},
            meta=meta))

    quizzes = ctx.dispatch.require(
        CourseViewSet, {'get': 'quizzes'},
        method='GET', path=f'/courses/{ctx.course.id}/quizzes/', pk=ctx.course.id,
        what='listing quizzes')
    rows = [shaping.project(q, ('id', 'title', 'assignment', 'published',
                                'isPublished', 'availability', 'timeLimitMinutes',
                                'maxAttempts', 'scoringPolicy', 'needsGrading'))
            for q in (quizzes or [])]

    if view == 'needsGrading':
        rows = [q for q in rows if q.get('needsGrading')]

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course), 'quizzes': rows},
        meta={'total': len(rows)},
        warnings=(['Per-student detail: codepost_get_quiz_status(view="results", '
                   'quizId=…).'] if rows else None)))
