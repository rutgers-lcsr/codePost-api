# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Quiz setup writes: compose a quiz from scratch, adjust it, manage questions.

The authoring chain the API expects is bank → questions (each with an answer
key) → quiz → QuizQuestion links → publish. ``codepost_create_quiz`` walks the
whole chain in one call because that is the task an instructor actually asks
for; the pieces stay reachable through ``codepost_edit_quiz_questions`` and
``codepost_update_quiz``.
"""
from __future__ import annotations

from core.agent import errors, shaping
from core.agent.registry import SCOPE_WRITE, tool
from core.agent.tools._common import course_header
from core.permissions.capabilities import Capability

_QUESTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'questionType': {'enum': ['multiple_choice', 'multiple_answers',
                                  'true_false', 'short_answer', 'essay']},
        'text': {'type': 'string', 'description': 'The question prompt.'},
        'points': {'type': 'number', 'description': 'Defaults to 1.'},
        'description': {'type': 'string',
                        'description': 'Optional Markdown below the prompt.'},
        'choices': {
            'type': 'array',
            'description': ('Required for choice-based types. For true_false '
                            'use two choices "True" and "False". short_answer '
                            'choices are the accepted answers (isCorrect true). '
                            'essay takes no choices and is manually graded.'),
            'items': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string'},
                    'isCorrect': {'type': 'boolean'},
                    'feedback': {'type': 'string'},
                },
                'required': ['text'],
            },
        },
    },
    'required': ['questionType', 'text'],
}

_QUIZ_SETTINGS = {
    'description': {'type': 'string'},
    'timeLimitMinutes': {'type': 'integer',
                         'description': 'Omit for untimed.'},
    'attemptsAllowed': {'type': 'integer',
                        'description': '0 = unlimited. Defaults to 1.'},
    'shuffleQuestions': {'type': 'boolean'},
    'oneQuestionAtATime': {'type': 'boolean'},
    'showCorrectAnswers': {'type': 'boolean'},
    'sealResultsUntilClose': {'type': 'boolean'},
    'passingScore': {'type': 'number'},
    'passingScoreUnit': {'enum': ['percent', 'points']},
    'scoringPolicy': {'enum': ['highest', 'latest', 'average']},
    'assignmentTrigger': {
        'enum': ['during', 'after_assignment', 'after_submission',
                 'after_feedback', 'after_student_feedback'],
        'description': 'Attached quizzes: when the quiz opens relative to the '
                       'assignment lifecycle. Ignored for standalone quizzes.'},
    'availableFrom': {'type': 'string',
                      'description': 'Standalone quizzes: ISO open time.'},
    'availableUntil': {'type': 'string',
                       'description': 'Standalone quizzes: ISO close time.'},
}


@tool(
    name='codepost_create_quiz',
    title='Create quiz',
    description=(
        'Create a complete quiz in one call: the questions (with answer keys), '
        'the quiz itself, and optionally an attachment to an assignment. The '
        'quiz ALWAYS lands unpublished — students cannot see it until '
        'codepost_update_quiz publishes it. dryRun=true (default) previews the '
        'whole plan first: check the questions and answer keys with the user '
        'before creating.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'title': {'type': 'string', 'maxLength': 128},
            'questions': {'type': 'array', 'items': _QUESTION_SCHEMA,
                          'minItems': 1},
            'assignmentId': {
                'type': 'integer',
                'description': 'Attach to this assignment (quiz opens per '
                               'assignmentTrigger). Omit for standalone.'},
            'bankId': {
                'type': 'integer',
                'description': 'Question bank to file questions in. Omitted: a '
                               'bank named after the quiz is created.'},
            **_QUIZ_SETTINGS,
            'dryRun': {'type': 'boolean', 'default': True},
        },
        'required': ['title', 'questions'],
        'additionalProperties': False,
    },
    capability=Capability.GRADE_QUIZ,
    min_scope=SCOPE_WRITE, tier=1,
    read_only=False, destructive=False, idempotent=False,
)
def create_quiz(ctx, title: str, questions: list, assignmentId=None, bankId=None,
                dryRun: bool = True, **settings):
    from core.views.question import QuestionViewSet
    from core.views.questionBank import QuestionBankViewSet
    from core.views.quiz import QuizViewSet
    from core.views.quizQuestion import QuizQuestionViewSet

    if assignmentId is not None:
        from core.agent.tools._common import fetch_assignment
        fetch_assignment(ctx, assignmentId)          # existence + scope check

    total_points = sum(float(q.get('points', 1)) for q in questions)
    auto_graded = [q for q in questions
                   if q.get('questionType') not in ('essay', 'short_answer')]
    keyless = [i for i, q in enumerate(auto_graded)
               if not any(c.get('isCorrect') for c in (q.get('choices') or []))]
    if keyless:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET',
            f'Auto-graded questions need at least one choice marked isCorrect; '
            f'question index(es) {keyless} have none.',
            remedy='Mark the correct choice(s) and call again.', retryable=True)

    plan = {
        'quiz': {'title': title, 'attachedToAssignment': assignmentId,
                 'published': False, **{k: v for k, v in settings.items()}},
        'questions': [{'index': i, 'type': q['questionType'],
                       'points': q.get('points', 1),
                       'text': (q['text'][:80] + '…') if len(q['text']) > 80
                               else q['text'],
                       'choices': len(q.get('choices') or []),
                       'correct': sum(1 for c in (q.get('choices') or [])
                                      if c.get('isCorrect'))}
                      for i, q in enumerate(questions)],
        'totalPoints': total_points,
        'bank': bankId or f"(new bank: '{title}')",
        'manuallyGraded': sum(1 for q in questions
                              if q.get('questionType') == 'essay'),
    }
    if dryRun:
        return shaping.enforce_budget(shaping.envelope(
            {'course': course_header(ctx.course), 'plan': plan},
            meta={'dryRun': True,
                  'hint': 'Review the questions and answer keys with the user, '
                          'then re-call with dryRun=false.'}))

    # 1. Bank
    if bankId is None:
        bank = ctx.dispatch.require(
            QuestionBankViewSet, {'post': 'create'},
            method='POST', path='/questionBanks/',
            data={'course': ctx.course.id, 'name': title[:128]},
            what='creating a question bank')
        bankId = bank['id']

    # 2. Questions — sequential, with a per-item failure report rather than a
    # half-silent batch.
    created_questions, failures = [], []
    for i, q in enumerate(questions):
        body = {'course': ctx.course.id, 'bank': bankId,
                'questionType': q['questionType'], 'text': q['text'],
                'points': q.get('points', 1)}
        if q.get('description'):
            body['description'] = q['description']
        if q.get('choices'):
            body['choices'] = q['choices']
        result = ctx.dispatch.call(
            QuestionViewSet, {'post': 'create'},
            method='POST', path='/questions/', data=body)
        if result.ok:
            created_questions.append(result.data['id'])
        else:
            failures.append({'index': i, 'detail': errors._stringify(result.data)})

    if not created_questions:
        raise errors.ToolError(
            'PARTIAL_FAILURE', 'No questions could be created; quiz not created.',
            remedy='Fix the reported problems and call again.', retryable=True,
            context={'failures': failures})

    # 3. Quiz (always unpublished — publishing is codepost_update_quiz's job)
    quiz_body = {'course': ctx.course.id, 'title': title, **settings}
    if assignmentId is not None:
        quiz_body['assignment'] = assignmentId
    quiz = ctx.dispatch.require(
        QuizViewSet, {'post': 'create'},
        method='POST', path='/quizzes/', data=quiz_body,
        what=f"creating quiz '{title}'")

    # 4. Links, in order
    for sort_key, question_id in enumerate(created_questions):
        ctx.dispatch.call(
            QuizQuestionViewSet, {'post': 'create'},
            method='POST', path='/quizQuestions/',
            data={'quiz': quiz['id'], 'question': question_id,
                  'sortKey': sort_key})

    payload = {'course': course_header(ctx.course),
               'quiz': {'id': quiz['id'], 'title': quiz['title'],
                        'isPublished': quiz.get('isPublished', False),
                        'assignment': quiz.get('assignment'),
                        'questionCount': len(created_questions),
                        'totalPoints': total_points,
                        'bankId': bankId}}
    warnings = ['The quiz is unpublished — students cannot see it. Publish '
                'with codepost_update_quiz(quizId=%d, publish=true).' % quiz['id']]
    if failures:
        warnings.append(f'{len(failures)} question(s) failed and were skipped: '
                        f'{failures}')
    return shaping.enforce_budget(shaping.envelope(payload, warnings=warnings))


@tool(
    name='codepost_update_quiz',
    title='Update or publish quiz',
    description=(
        'Change quiz settings, or publish/unpublish it. Publishing makes the '
        'quiz visible to students per its availability rules — dryRun=true '
        '(default when publish is set) previews question count, total points '
        'and availability first.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'quizId': {'type': 'integer'},
            'title': {'type': 'string', 'maxLength': 128},
            'publish': {'type': 'boolean',
                        'description': 'true publishes, false unpublishes.'},
            **_QUIZ_SETTINGS,
            'dryRun': {'type': 'boolean', 'default': True},
        },
        'required': ['quizId'],
        'additionalProperties': False,
    },
    capability=Capability.GRADE_QUIZ,
    min_scope=SCOPE_WRITE, tier=1,
    read_only=False, destructive=False, idempotent=True,
)
def update_quiz(ctx, quizId: int, publish=None, dryRun: bool = True, **settings):
    from core.views.quiz import QuizViewSet

    quiz = ctx.dispatch.require(
        QuizViewSet, {'get': 'retrieve'},
        method='GET', path=f'/quizzes/{quizId}/', pk=quizId,
        what=f'reading quiz {quizId}')
    ctx.dispatch.assert_in_scope(quiz.get('course'), what=f'quiz {quizId}')

    question_count = len(quiz.get('quizQuestions') or [])
    warnings = []
    if publish is True and question_count == 0:
        warnings.append('This quiz has ZERO questions — publishing it would '
                        'show students an empty quiz.')

    if dryRun and publish is not None:
        plan = {'quiz': {'id': quizId, 'title': quiz.get('title')},
                'publish': publish,
                'questionCount': question_count,
                'attachedAssignment': quiz.get('assignment'),
                'availability': {
                    'assignmentTrigger': quiz.get('assignmentTrigger'),
                    'availableFrom': quiz.get('availableFrom'),
                    'availableUntil': quiz.get('availableUntil')},
                'settingsChanges': sorted(settings)}
        return shaping.envelope(
            {'course': course_header(ctx.course), 'plan': plan},
            meta={'dryRun': True,
                  'hint': 'Re-call with dryRun=false to apply.'},
            warnings=warnings or None)

    body = dict(settings)
    if publish is not None:
        body['isPublished'] = publish
    if not body:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET', 'Nothing to change.',
            remedy='Pass settings fields and/or publish.', retryable=True)

    data = ctx.dispatch.require(
        QuizViewSet, {'patch': 'partial_update'},
        method='PATCH', path=f'/quizzes/{quizId}/', data=body, pk=quizId,
        what=f'updating quiz {quizId}')

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course),
         'quiz': {'id': data.get('id'), 'title': data.get('title'),
                  'isPublished': data.get('isPublished'),
                  'questionCount': question_count},
         'changed': sorted(body)},
        warnings=warnings or None))


@tool(
    name='codepost_edit_quiz_questions',
    title='Edit quiz questions',
    description=(
        'Add, remove or reorder the questions on an existing quiz. New '
        'questions are created in the given bank (or the quiz title bank) and '
        'linked; removing unlinks from this quiz without deleting the reusable '
        'question. Editing a PUBLISHED quiz changes what students see — the '
        'warning will say so.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'quizId': {'type': 'integer'},
            'add': {'type': 'array', 'items': _QUESTION_SCHEMA,
                    'description': 'New questions to create and append.'},
            'addExistingQuestionIds': {'type': 'array',
                                       'items': {'type': 'integer'}},
            'removeQuizQuestionIds': {
                'type': 'array', 'items': {'type': 'integer'},
                'description': 'QuizQuestion link ids (from the quiz detail), '
                               'not question ids.'},
            'bankId': {'type': 'integer'},
        },
        'required': ['quizId'],
        'additionalProperties': False,
    },
    capability=Capability.GRADE_QUIZ,
    min_scope=SCOPE_WRITE, tier=0,
    read_only=False, destructive=False, idempotent=False,
)
def edit_quiz_questions(ctx, quizId: int, add=None, addExistingQuestionIds=None,
                        removeQuizQuestionIds=None, bankId=None):
    from core.views.question import QuestionViewSet
    from core.views.questionBank import QuestionBankViewSet
    from core.views.quiz import QuizViewSet
    from core.views.quizQuestion import QuizQuestionViewSet

    quiz = ctx.dispatch.require(
        QuizViewSet, {'get': 'retrieve'},
        method='GET', path=f'/quizzes/{quizId}/', pk=quizId,
        what=f'reading quiz {quizId}')
    ctx.dispatch.assert_in_scope(quiz.get('course'), what=f'quiz {quizId}')

    existing_links = quiz.get('quizQuestions') or []
    next_sort = max((l.get('sortKey', 0) for l in existing_links), default=-1) + 1
    report = {'added': [], 'linked': [], 'removed': [], 'failures': []}

    for i, q in enumerate(add or []):
        if bankId is None:
            bank = ctx.dispatch.require(
                QuestionBankViewSet, {'post': 'create'},
                method='POST', path='/questionBanks/',
                data={'course': ctx.course.id,
                      'name': (quiz.get('title') or 'Quiz')[:128]},
                what='creating a question bank')
            bankId = bank['id']
        body = {'course': ctx.course.id, 'bank': bankId,
                'questionType': q['questionType'], 'text': q['text'],
                'points': q.get('points', 1)}
        if q.get('choices'):
            body['choices'] = q['choices']
        result = ctx.dispatch.call(QuestionViewSet, {'post': 'create'},
                                   method='POST', path='/questions/', data=body)
        if not result.ok:
            report['failures'].append({'op': 'add', 'index': i,
                                       'detail': errors._stringify(result.data)})
            continue
        link = ctx.dispatch.call(
            QuizQuestionViewSet, {'post': 'create'},
            method='POST', path='/quizQuestions/',
            data={'quiz': quizId, 'question': result.data['id'],
                  'sortKey': next_sort})
        next_sort += 1
        report['added'].append(result.data['id'])
        if not link.ok:
            report['failures'].append({'op': 'link', 'index': i,
                                       'detail': errors._stringify(link.data)})

    for qid in (addExistingQuestionIds or []):
        link = ctx.dispatch.call(
            QuizQuestionViewSet, {'post': 'create'},
            method='POST', path='/quizQuestions/',
            data={'quiz': quizId, 'question': qid, 'sortKey': next_sort})
        next_sort += 1
        if link.ok:
            report['linked'].append(qid)
        else:
            report['failures'].append({'op': 'addExisting', 'questionId': qid,
                                       'detail': errors._stringify(link.data)})

    for link_id in (removeQuizQuestionIds or []):
        result = ctx.dispatch.call(
            QuizQuestionViewSet, {'delete': 'destroy'},
            method='DELETE', path=f'/quizQuestions/{link_id}/', pk=link_id)
        if result.ok:
            report['removed'].append(link_id)
        else:
            report['failures'].append({'op': 'remove', 'quizQuestionId': link_id,
                                       'detail': errors._stringify(result.data)})

    warnings = []
    if quiz.get('isPublished'):
        warnings.append('This quiz is PUBLISHED — students see these changes '
                        'immediately.')
    if report['failures']:
        warnings.append('Some operations failed; see failures in the result. '
                        'Re-call with only the failed items.')

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course),
         'quiz': {'id': quizId, 'title': quiz.get('title'),
                  'isPublished': quiz.get('isPublished')},
         'report': report},
        warnings=warnings or None))
