# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tier-3 tools: unrecoverable destruction and mass email.

Every tool here requires an ``admin``-scope key AND a real human decision the
agent cannot fabricate: on elicitation-capable clients the MCP client shows an
Approve/Decline dialog in the chat UI (the model never sees it); elsewhere the
operation waits on the Approve button in Course Settings → Pending agent
actions, whose endpoints refuse course-scoped credentials. Approvals are
single-use, expire in 10 minutes, and die if the operation's blast radius
changes between preview and approval.
"""
from __future__ import annotations

from core.agent import errors, guardrails, shaping
from core.agent.registry import SCOPE_ADMIN, tool
from core.agent.tools._common import course_header, fetch_assignment
from core.permissions.capabilities import Capability


@tool(
    name='codepost_delete_resource',
    title='Delete a resource',
    description=(
        'PERMANENTLY delete an assignment, section, quiz, test category or '
        'question bank. The user must approve it first — via the approval '
        'dialog your client shows, or the Approve button in the codePost '
        'dashboard (the refusal includes the link). Deleting an assignment '
        'that has submissions is refused entirely: archive it with '
        'codepost_set_assignment_stage instead.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'resourceType': {'enum': ['assignment', 'section', 'quiz',
                                      'testCategory', 'questionBank']},
            'resourceId': {'type': 'integer'},
        },
        'required': ['resourceType', 'resourceId'],
        'additionalProperties': False,
    },
    capability=Capability.VIEW_COURSE,
    min_scope=SCOPE_ADMIN, tier=3,
    read_only=False, destructive=True, idempotent=False,
)
def delete_resource(ctx, resourceType: str, resourceId: int):
    view_cls, path_root, plan = _blast_radius(ctx, resourceType, resourceId)

    args = {'resourceType': resourceType, 'resourceId': resourceId}
    message = (f"This PERMANENTLY deletes {resourceType} "
               f"'{plan.get('name', resourceId)}'"
               + (f" and everything listed in the plan" if plan.get('cascades')
                  else '') + '.')

    guardrails.require_human_confirmation(
        'codepost_delete_resource', args, plan, ctx=ctx, message=message)

    ctx.dispatch.require(
        view_cls, {'delete': 'destroy'},
        method='DELETE', path=f'/{path_root}/{resourceId}/', pk=resourceId,
        what=f'deleting {resourceType} {resourceId}')

    return shaping.envelope(
        {'course': course_header(ctx.course),
         'deleted': {'type': resourceType, 'id': resourceId,
                     'name': plan.get('name')}},
        warnings=['This deletion is permanent.'])


def _blast_radius(ctx, resource_type: str, resource_id: int):
    """Resolve the target, prove it is in scope, and describe what dies with it."""
    if resource_type == 'assignment':
        from core.views.assignment import AssignmentViewSet

        a = fetch_assignment(ctx, resource_id)
        submissions = a.get('submissionsCount') or 0
        if submissions:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET',
                f"Assignment '{a.get('name')}' has {submissions} submissions — "
                'deleting it would destroy student work, so this tool refuses '
                'outright.',
                remedy="Retire it instead: codepost_set_assignment_stage("
                       f"assignmentId={resource_id}, targetStage='archived').")
        quizzes = ctx.dispatch.call(
            AssignmentViewSet, {'get': 'quizzes'},
            method='GET', path=f'/assignments/{resource_id}/quizzes/',
            pk=resource_id)
        quiz_titles = [q.get('title') for q in (quizzes.data or [])] \
            if quizzes.ok else []
        return AssignmentViewSet, 'assignments', {
            'name': a.get('name'), 'state': a.get('state'),
            'cascades': {'rubric': 'all categories and comments',
                         'testCategories': len(a.get('testCategories') or []),
                         'files': len(a.get('files') or []),
                         'attachedQuizzes': quiz_titles}}

    if resource_type == 'section':
        from core.views.section import SectionViewSet

        s = ctx.dispatch.require(
            SectionViewSet, {'get': 'retrieve'},
            method='GET', path=f'/sections/{resource_id}/', pk=resource_id,
            what=f'reading section {resource_id}')
        ctx.dispatch.assert_in_scope(s.get('course'), what=f'section {resource_id}')
        return SectionViewSet, 'sections', {
            'name': s.get('name'),
            'cascades': {'studentsUnassigned': len(s.get('students') or []),
                         'note': 'Students stay in the course.'}}

    if resource_type == 'quiz':
        from core.views.quiz import QuizViewSet

        q = ctx.dispatch.require(
            QuizViewSet, {'get': 'retrieve'},
            method='GET', path=f'/quizzes/{resource_id}/', pk=resource_id,
            what=f'reading quiz {resource_id}')
        ctx.dispatch.assert_in_scope(q.get('course'), what=f'quiz {resource_id}')
        return QuizViewSet, 'quizzes', {
            'name': q.get('title'), 'isPublished': q.get('isPublished'),
            'cascades': {'questionLinks': len(q.get('quizQuestions') or []),
                         'note': 'Student attempts and responses are deleted '
                                 'with the quiz. Reusable questions stay in '
                                 'their banks.'}}

    if resource_type == 'testCategory':
        from core.views.testCategory import TestCategoryViewSet

        t = ctx.dispatch.require(
            TestCategoryViewSet, {'get': 'retrieve'},
            method='GET', path=f'/testCategories/{resource_id}/', pk=resource_id,
            what=f'reading test category {resource_id}')
        return TestCategoryViewSet, 'testCategories', {
            'name': t.get('name'),
            'cascades': {'testCases': len(t.get('testCases') or []),
                         'note': 'Past test results on submissions are '
                                 'deleted with their cases.'}}

    # questionBank
    from core.views.questionBank import QuestionBankViewSet

    b = ctx.dispatch.require(
        QuestionBankViewSet, {'get': 'retrieve'},
        method='GET', path=f'/questionBanks/{resource_id}/', pk=resource_id,
        what=f'reading question bank {resource_id}')
    ctx.dispatch.assert_in_scope(b.get('course'), what=f'bank {resource_id}')
    return QuestionBankViewSet, 'questionBanks', {
        'name': b.get('name'),
        'cascades': {'questions': b.get('questionCount'),
                     'note': 'Questions in this bank are deleted, including '
                             'their use in quizzes.'}}


@tool(
    name='codepost_reset_quiz_attempts',
    title='Reset quiz attempts',
    description=(
        "PERMANENTLY delete every student's attempts (and answers, and any "
        'manual grading already done) on a quiz, so everyone retakes from '
        'scratch. Use after a substantive quiz edit. The user must approve '
        'it first — via the approval dialog your client shows, or the Approve '
        'button in the codePost dashboard.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'quizId': {'type': 'integer'},
        },
        'required': ['quizId'],
        'additionalProperties': False,
    },
    capability=Capability.GRADE_QUIZ,
    min_scope=SCOPE_ADMIN, tier=3,
    read_only=False, destructive=True, idempotent=False,
)
def reset_quiz_attempts(ctx, quizId: int):
    from core.views.quiz import QuizViewSet

    quiz = ctx.dispatch.require(
        QuizViewSet, {'get': 'retrieve'},
        method='GET', path=f'/quizzes/{quizId}/', pk=quizId,
        what=f'reading quiz {quizId}')
    ctx.dispatch.assert_in_scope(quiz.get('course'), what=f'quiz {quizId}')

    results = ctx.dispatch.call(
        QuizViewSet, {'get': 'results'},
        method='GET', path=f'/quizzes/{quizId}/results/', pk=quizId)
    rows = results.data if results.ok and isinstance(results.data, list) else []
    plan = {
        'quiz': {'id': quizId, 'title': quiz.get('title'),
                 'isPublished': quiz.get('isPublished')},
        'studentsWithAttempts': len(rows),
        'attemptsUsed': sum(r.get('attemptsUsed') or 0 for r in rows),
        'gradedWorkDiscarded': sum(1 for r in rows if r.get('score') is not None),
    }
    args = {'quizId': quizId}

    guardrails.require_human_confirmation(
        'codepost_reset_quiz_attempts', args, plan, ctx=ctx,
        message=f"This deletes {plan['attemptsUsed']} attempts from "
                f"{plan['studentsWithAttempts']} students on "
                f"'{quiz.get('title')}', including "
                f"{plan['gradedWorkDiscarded']} graded results.")

    result = ctx.dispatch.require(
        QuizViewSet, {'post': 'resetAttempts'},
        method='POST', path=f'/quizzes/{quizId}/resetAttempts/', pk=quizId,
        what=f'resetting attempts on quiz {quizId}')

    return shaping.envelope(
        {'course': course_header(ctx.course),
         'quiz': {'id': quizId, 'title': quiz.get('title')},
         'deletedAttempts': result.get('deleted')},
        warnings=['All attempts are gone; students can now retake from scratch.'])


@tool(
    name='codepost_notify_students_feedback_ready',
    title='Email students their feedback is ready',
    description=(
        'Send every eligible student on an assignment a REAL EMAIL saying '
        'their feedback is ready. Only finalized submissions with open '
        'feedback qualify — the preview shows exactly who would be emailed '
        '(and who is skipped, and why), and the user must approve the send — '
        'via the approval dialog your client shows, or the Approve button in '
        'the codePost dashboard.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'assignmentId': {'type': 'integer'},
        },
        'required': ['assignmentId'],
        'additionalProperties': False,
    },
    capability=Capability.VIEW_COURSE,
    min_scope=SCOPE_ADMIN, tier=3,
    read_only=False, destructive=False, idempotent=False,
)
def notify_students_feedback_ready(ctx, assignmentId: int):
    from core.views.assignment import AssignmentViewSet
    from core.views.submission import SubmissionViewSet

    assignment = fetch_assignment(ctx, assignmentId)
    feedback_open = assignment.get('feedbackStatus') in ('live', 'released',
                                                         'per_student')
    if not feedback_open:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET',
            f"Feedback on '{assignment.get('name')}' is "
            f"'{assignment.get('feedbackStatus')}' — students would click "
            'through to nothing.',
            remedy='Release feedback first with codepost_set_feedback_stage.')

    rows = ctx.dispatch.require(
        AssignmentViewSet, {'get': 'submissions'},
        method='GET', path=f'/assignments/{assignmentId}/submissions/',
        query='compact=1', pk=assignmentId,
        what='listing submissions to notify')
    rows = rows if isinstance(rows, list) else []

    # Pre-filter to the submissions the endpoint would accept: it 406s on
    # anything unfinalized, and an agent reading a string of 406s one at a
    # time tends to conclude the release failed and start undoing things.
    eligible = [r for r in rows if r.get('isFinalized')]
    skipped_unfinalized = len(rows) - len(eligible)
    recipients = sorted({e for r in eligible for e in (r.get('students') or [])})

    if not eligible:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET', 'No finalized submissions to notify.',
            remedy='Check codepost_get_grading_progress.')

    plan = {
        'assignment': {'id': assignmentId, 'name': assignment.get('name')},
        'emailsToSend': len(recipients),
        'sampleRecipients': recipients[:10],
        'skipped': {'unfinalized': skipped_unfinalized},
    }
    args = {'assignmentId': assignmentId}

    guardrails.require_human_confirmation(
        'codepost_notify_students_feedback_ready', args, plan, ctx=ctx,
        message=f"This emails {len(recipients)} students that feedback on "
                f"'{assignment.get('name')}' is ready.")

    sent, failures = 0, []
    for row in eligible:
        result = ctx.dispatch.call(
            SubmissionViewSet, {'post': 'notifyStudents'},
            method='POST', path=f"/submissions/{row['id']}/notifyStudents/",
            pk=row['id'])
        if result.ok:
            sent += 1
        else:
            failures.append({'submissionId': row['id'],
                             'detail': errors._stringify(result.data)})

    return shaping.envelope(
        {'course': course_header(ctx.course),
         'assignment': {'id': assignmentId, 'name': assignment.get('name')},
         'notifiedSubmissions': sent,
         'skipped': plan['skipped'],
         'failures': failures},
        warnings=(['Some notifications failed — see failures.'] if failures
                  else None))
