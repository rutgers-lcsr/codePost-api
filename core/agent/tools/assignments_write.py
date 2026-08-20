# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Assignment setup and lifecycle writes.

The lifecycle policy lives HERE, deliberately: the API accepts any state →
state PATCH (there is no transition table server-side), including
``published → draft``, which wipes ``publishedAt`` and revokes students'
access to their own submissions. See docs/assignment_lifecycle.md — the
state table in the dry-run previews is transcribed from it.
"""
from __future__ import annotations

from core.agent import errors, guardrails, shaping
from core.agent.registry import SCOPE_WRITE, tool
from core.agent.tools._common import (ASSIGNMENT_SUMMARY_FIELDS, course_header,
                                      fetch_assignment)
from core.permissions.capabilities import Capability

# Work axis, in student-visibility order (docs/assignment_lifecycle.md).
_STATES = ('draft', 'visible', 'preview', 'published', 'closed', 'archived')
_STATE_ORDER = {s: i for i, s in enumerate(_STATES)}

# What each state means for students — rendered into every dry-run so the
# instructor sees consequences, not state names.
_STUDENT_TABLE = {
    'draft':     {'canSeeAssignment': False, 'canDownloadFiles': False,
                  'canSubmit': False, 'canViewOwnSubmission': False},
    'visible':   {'canSeeAssignment': True, 'canDownloadFiles': False,
                  'canSubmit': False, 'canViewOwnSubmission': False},
    'preview':   {'canSeeAssignment': True, 'canDownloadFiles': True,
                  'canSubmit': False, 'canViewOwnSubmission': False},
    'published': {'canSeeAssignment': True, 'canDownloadFiles': True,
                  'canSubmit': True, 'canViewOwnSubmission': True},
    'closed':    {'canSeeAssignment': True, 'canDownloadFiles': True,
                  'canSubmit': False, 'canViewOwnSubmission': True},
    'archived':  {'canSeeAssignment': False, 'canDownloadFiles': False,
                  'canSubmit': False, 'canViewOwnSubmission': False},
}

_FEEDBACK_STAGES = ('hidden', 'live', 'perStudent', 'released')
_FEEDBACK_WIRE = {'hidden': 'hidden', 'live': 'live',
                  'perStudent': 'per_student', 'released': 'released'}

# The writable, non-lifecycle assignment settings. state/feedbackStatus/
# publishAt/releaseFeedbackAt/hideGrades are deliberately absent — the
# lifecycle tools own those — as are the ai_* prompt fields.
_SETTINGS_PROPERTIES = {
    'name': {'type': 'string', 'maxLength': 32},
    'points': {'type': 'number'},
    'explanation': {'type': 'string',
                    'description': 'The assignment description students see.'},
    'uploadDueDate': {'type': 'string',
                      'description': 'ISO datetime. On a published assignment, '
                                     'moving this moves the derived close.'},
    'allowStudentUpload': {'type': 'boolean'},
    'allowStudentUploadWithPartners': {'type': 'boolean'},
    'allowLateUploads': {'type': 'boolean'},
    'maxLateDays': {'type': 'integer'},
    'anonymousGrading': {'type': 'boolean'},
    'additiveGrading': {'type': 'boolean'},
    'allowRegradeRequests': {'type': 'boolean'},
    'regradeDeadline': {'type': 'string'},
    'regradeInstructions': {'type': 'string'},
    'forcedRubricMode': {'type': 'boolean'},
    'gradersCanEditSubmissions': {'type': 'boolean'},
    'studentsCanSeeGraders': {'type': 'boolean'},
    'runTestsOnSubmit': {'type': 'boolean'},
    'testsAffectGrade': {'type': 'boolean'},
    'sortKey': {'type': 'integer'},
}


@tool(
    name='codepost_create_assignment',
    title='Create assignment',
    description=(
        'Create a new assignment. It ALWAYS lands as a hidden draft — students '
        'cannot see it until codepost_set_assignment_stage moves it forward, '
        'so creating is safe to do freely. Set allowStudentUpload=true here if '
        'students will submit through codePost.'
    ),
    input_schema={
        'type': 'object',
        'properties': {'name': _SETTINGS_PROPERTIES['name'],
                       'points': _SETTINGS_PROPERTIES['points'],
                       **{k: v for k, v in _SETTINGS_PROPERTIES.items()
                          if k not in ('name', 'points')}},
        'required': ['name', 'points'],
        'additionalProperties': False,
    },
    capability=Capability.CREATE_ASSIGNMENT,
    min_scope=SCOPE_WRITE, tier=1,
    read_only=False, destructive=False, idempotent=False,
)
def create_assignment(ctx, name: str, points, **settings):
    from core.views.assignment import AssignmentViewSet

    body = {'course': ctx.course.id, 'name': name, 'points': points, **settings}
    data = ctx.dispatch.require(
        AssignmentViewSet, {'post': 'create'},
        method='POST', path='/assignments/', data=body,
        what=f"creating assignment '{name}'")

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course),
         'assignment': shaping.project(data, ASSIGNMENT_SUMMARY_FIELDS)},
        warnings=[
            "Created as a hidden draft (state='draft', feedback hidden). Use "
            'codepost_set_assignment_stage to make it visible to students.',
        ] + ([] if settings.get('allowStudentUpload') else [
            'allowStudentUpload is false — students will not be able to submit '
            'even once published. Set it via codepost_update_assignment if '
            'they should.',
        ])))


@tool(
    name='codepost_update_assignment',
    title='Update assignment settings',
    description=(
        'Change assignment settings: name, points, deadline, late policy, '
        'grading options. This tool CANNOT change student visibility or '
        'feedback release — use codepost_set_assignment_stage and '
        'codepost_set_feedback_stage for those.'
    ),
    input_schema={
        'type': 'object',
        'properties': {'assignmentId': {'type': 'integer'},
                       **_SETTINGS_PROPERTIES},
        'required': ['assignmentId'],
        'additionalProperties': False,
    },
    capability=Capability.VIEW_COURSE,
    min_scope=SCOPE_WRITE, tier=0,
    read_only=False, destructive=False, idempotent=True,
)
def update_assignment(ctx, assignmentId: int, **changes):
    from core.views.assignment import AssignmentViewSet

    if not changes:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET', 'No settings were provided to change.',
            remedy='Pass at least one settings field.', retryable=True)

    before = fetch_assignment(ctx, assignmentId)
    data = ctx.dispatch.require(
        AssignmentViewSet, {'patch': 'partial_update'},
        method='PATCH', path=f'/assignments/{assignmentId}/', data=changes,
        pk=assignmentId, what=f'updating assignment {assignmentId}')

    warnings = []
    if 'uploadDueDate' in changes and before.get('state') in ('published', 'closed'):
        effective = data.get('effectiveState')
        warnings.append(
            f"The submission deadline moved; the assignment now reads as "
            f"'{effective}' to students (derived close follows the deadline).")

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course),
         'assignment': shaping.project(data, ASSIGNMENT_SUMMARY_FIELDS),
         'changed': sorted(changes)},
        warnings=warnings or None))


@tool(
    name='codepost_clone_assignment',
    title='Clone assignment',
    description=(
        'Duplicate an assignment within this course, including its rubric, test '
        'cases, autograder environment and datasets. The clone lands as an '
        'inert hidden draft with no deadline and uploads off. Preview first: '
        'dryRun=true (the default) shows exactly what carries over and what '
        'resets.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'sourceAssignmentId': {'type': 'integer'},
            'newName': {'type': 'string', 'maxLength': 32},
            'uploadDueDate': {'type': 'string',
                              'description': 'ISO datetime for the clone.'},
            'allowStudentUpload': {'type': 'boolean'},
            'dryRun': {'type': 'boolean', 'default': True},
        },
        'required': ['sourceAssignmentId'],
        'additionalProperties': False,
    },
    capability=Capability.CREATE_ASSIGNMENT,
    min_scope=SCOPE_WRITE, tier=1,
    read_only=False, destructive=False, idempotent=False,
)
def clone_assignment(ctx, sourceAssignmentId: int, newName: str = '',
                     uploadDueDate: str = '', allowStudentUpload=None,
                     dryRun: bool = True):
    from core.views.assignment import AssignmentViewSet

    source = fetch_assignment(ctx, sourceAssignmentId)

    plan = {
        'source': {'id': source.get('id'), 'name': source.get('name')},
        'willCopy': ['assignment files', 'rubric categories and comments',
                     'test categories and cases', 'autograder environment',
                     'datasets', 'AI prompts'],
        # copy_assignment (core/utils.py) resets these deliberately.
        'willReset': ["state → 'draft'", "feedbackStatus → 'hidden'",
                      'allowStudentUpload → false', 'uploadDueDate → null',
                      'regradeDeadline → null', 'hideFrom → cleared'],
        'thenPatch': {k: v for k, v in (('name', newName),
                                        ('uploadDueDate', uploadDueDate),
                                        ('allowStudentUpload', allowStudentUpload))
                      if v not in ('', None)},
    }
    if dryRun:
        return shaping.envelope(
            {'course': course_header(ctx.course), 'plan': plan},
            meta={'dryRun': True,
                  'hint': 'Re-call with dryRun=false to clone.'})

    created = ctx.dispatch.require(
        AssignmentViewSet, {'post': 'clone'},
        method='POST', path=f'/assignments/{sourceAssignmentId}/clone/',
        data={'course': ctx.course.id}, pk=sourceAssignmentId,
        what=f'cloning assignment {sourceAssignmentId}')

    new_id = created.get('id')
    patch = plan['thenPatch']
    if patch and new_id:
        created = ctx.dispatch.require(
            AssignmentViewSet, {'patch': 'partial_update'},
            method='PATCH', path=f'/assignments/{new_id}/', data=patch, pk=new_id,
            what=f'renaming cloned assignment {new_id}')

    warnings = []
    if not created.get('allowStudentUpload'):
        warnings.append(
            'allowStudentUpload is false on the clone (the clone API resets '
            'it). Students cannot submit even after publishing — set it with '
            'codepost_update_assignment if they should.')
    failed_datasets = created.get('datasetsFailedToCopy') or []
    if failed_datasets:
        warnings.append(f'Datasets failed to copy: {failed_datasets}')

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course),
         'assignment': shaping.project(created, ASSIGNMENT_SUMMARY_FIELDS)},
        warnings=warnings or None))


@tool(
    name='codepost_set_assignment_stage',
    title='Set assignment stage',
    description=(
        'Move an assignment along its student-visibility lifecycle: '
        'draft → visible (announced) → preview (spec downloadable) → published '
        '(submissions open, if allowStudentUpload) → closed → archived. '
        'Publishing does NOT reveal grades — that is codepost_set_feedback_stage. '
        'A published assignment past its deadline already reads as closed '
        'automatically. dryRun=true (default) previews exactly what students '
        'gain or lose.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'assignmentId': {'type': 'integer'},
            'targetStage': {'enum': list(_STATES)},
            'scheduleAt': {'type': 'string',
                           'description': 'ISO datetime to auto-publish. Only '
                                          "valid when targetStage is 'visible' "
                                          "or 'preview'."},
            'dryRun': {'type': 'boolean', 'default': True},
            'confirmToken': {'type': 'string'},
        },
        'required': ['assignmentId', 'targetStage'],
        'additionalProperties': False,
    },
    capability=Capability.VIEW_COURSE,
    min_scope=SCOPE_WRITE, tier=2,
    read_only=False, destructive=True, idempotent=True,
)
def set_assignment_stage(ctx, assignmentId: int, targetStage: str,
                         scheduleAt: str = '', dryRun: bool = True,
                         confirmToken: str = ''):
    from core.views.assignment import AssignmentViewSet

    assignment = fetch_assignment(ctx, assignmentId)
    current = assignment.get('state')
    submissions = assignment.get('submissionsCount') or 0

    if targetStage == current and not scheduleAt:
        return shaping.envelope(
            {'course': course_header(ctx.course), 'changed': False,
             'state': current},
            meta={'note': 'Already in that stage; nothing written.'})

    classification = _classify(current, targetStage)

    # The one hard block: unpublishing student work. Students lose access to
    # their own submissions and publishedAt is wiped — the API allows it
    # silently, so the refusal has to live here.
    if classification == 'unpublish' and submissions > 0:
        raise errors.ToolError(
            'ILLEGAL_TRANSITION',
            f"Cannot move '{assignment.get('name')}' from '{current}' back to "
            f"'{targetStage}': {submissions} submissions exist. Students would "
            f'lose access to their own work and publishedAt would be cleared.',
            remedy="Use targetStage='closed' to stop new submissions while "
                   "students keep access, or 'archived' to retire it.",
            context={'from': current, 'to': targetStage,
                     'submissionsCount': submissions,
                     'suggestedTargets': ['closed', 'archived']})

    if scheduleAt and targetStage not in ('visible', 'preview'):
        raise errors.ToolError(
            'PRECONDITION_NOT_MET',
            "scheduleAt only applies when targetStage is 'visible' or 'preview' "
            '(the auto-publish sweep never publishes drafts, and a published '
            'assignment has nothing to schedule).',
            remedy='Drop scheduleAt, or target visible/preview.', retryable=True)

    plan = _stage_plan(assignment, current, targetStage, classification, scheduleAt)
    args = {'assignmentId': assignmentId, 'targetStage': targetStage,
            'scheduleAt': scheduleAt}

    # Only the zero-submission unpublish reaches here (with submissions it
    # was blocked above); it still hides an announced assignment, so gate it.
    needs_token = classification == 'unpublish'
    if dryRun:
        preview = {'course': course_header(ctx.course), 'plan': plan}
        if needs_token:
            raise guardrails.confirmation_required(
                'codepost_set_assignment_stage', args, plan,
                course_id=ctx.course.id, user_id=ctx.user.pk,
                message=f"Moving '{assignment.get('name')}' {current} → "
                        f'{targetStage} is a backward transition. Review the '
                        'plan, then confirm.')
        return shaping.envelope(preview, meta={
            'dryRun': True, 'hint': 'Re-call with dryRun=false to apply.'})

    if needs_token:
        guardrails.verify_token(confirmToken, 'codepost_set_assignment_stage',
                                args, plan, course_id=ctx.course.id,
                                user_id=ctx.user.pk)

    body = {'state': targetStage}
    if scheduleAt:
        body['publishAt'] = scheduleAt
    data = ctx.dispatch.require(
        AssignmentViewSet, {'patch': 'partial_update'},
        method='PATCH', path=f'/assignments/{assignmentId}/', data=body,
        pk=assignmentId, what=f'setting assignment {assignmentId} stage')

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course), 'changed': True,
         'from': current, 'to': data.get('state'),
         'effectiveState': data.get('effectiveState'),
         'publishAt': data.get('publishAt')},
        warnings=plan.get('warnings') or None))


def _classify(current: str, target: str) -> str:
    ci, ti = _STATE_ORDER.get(current, 0), _STATE_ORDER[target]
    if current == 'archived':
        return 'restore'
    if current in ('published', 'closed') and target in ('draft', 'visible', 'preview'):
        return 'unpublish'
    if current == 'closed' and target == 'published':
        return 'reopen'
    if ti > ci + 1:
        return 'forwardSkip'
    if ti > ci:
        return 'forward'
    return 'backward'


def _stage_plan(assignment, current, target, classification, schedule_at) -> dict:
    impact = {}
    before, after = _STUDENT_TABLE[current], _STUDENT_TABLE[target]
    for key in before:
        impact[key] = {'before': before[key], 'after': after[key]}
    impact['canSeeGradesOrComments'] = {
        'before': False, 'after': False,
        'note': f"feedbackStatus is '{assignment.get('feedbackStatus')}'; "
                'unchanged by this tool.',
    }

    warnings = []
    if classification == 'forwardSkip':
        warnings.append(f'Skipping intermediate stages between {current} and {target}.')
    if classification == 'reopen' and assignment.get('effectiveState') == 'closed' \
            and assignment.get('state') == 'published':
        pass
    if target == 'published' and not assignment.get('allowStudentUpload'):
        warnings.append('allowStudentUpload is false — students will see the '
                        'assignment but cannot submit.')
    if classification == 'reopen':
        warnings.append('If uploadDueDate is in the past, the derived close '
                        're-closes it immediately; extend the due date via '
                        'codepost_update_assignment instead.')

    side_effects = []
    if target == 'published':
        side_effects.append('publishedAt will be stamped.')
        if assignment.get('publishAt'):
            side_effects.append('publishAt will be cleared (moot once published).')
    if classification == 'unpublish':
        side_effects.append('publishedAt will be cleared.')
    if schedule_at:
        side_effects.append(f'publishAt set to {schedule_at} — the 5-minute '
                            'sweep auto-publishes it then.')

    return {'assignment': {'id': assignment.get('id'), 'name': assignment.get('name')},
            'from': current, 'to': target, 'classification': classification,
            'studentImpact': impact, 'sideEffects': side_effects,
            'warnings': warnings}


@tool(
    name='codepost_set_feedback_stage',
    title='Set feedback stage',
    description=(
        'Control whether students can see their grades, comments, rubric and '
        "full test results. Stages: 'hidden' (grading in progress), 'live' "
        "(visible as written), 'perStudent' (each student sees theirs once "
        "their submission is finalized), 'released' (all finalized submissions "
        'revealed at once). Independent of assignment visibility. hideGrades '
        'masks numeric scores in any revealing stage. dryRun=true (default) '
        'previews who gains access.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'assignmentId': {'type': 'integer'},
            'targetStage': {'enum': list(_FEEDBACK_STAGES)},
            'hideGrades': {'type': 'boolean'},
            'scheduleAt': {'type': 'string',
                           'description': 'ISO datetime to auto-release. Only '
                                          "valid from 'hidden' or 'perStudent'."},
            'dryRun': {'type': 'boolean', 'default': True},
            'confirmToken': {'type': 'string'},
        },
        'required': ['assignmentId', 'targetStage'],
        'additionalProperties': False,
    },
    capability=Capability.VIEW_COURSE,
    min_scope=SCOPE_WRITE, tier=2,
    read_only=False, destructive=True, idempotent=True,
)
def set_feedback_stage(ctx, assignmentId: int, targetStage: str, hideGrades=None,
                       scheduleAt: str = '', dryRun: bool = True,
                       confirmToken: str = ''):
    from core.views.assignment import AssignmentViewSet

    assignment = fetch_assignment(ctx, assignmentId)
    current_wire = assignment.get('feedbackStatus')
    target_wire = _FEEDBACK_WIRE[targetStage]

    total = assignment.get('submissionsCount') or 0
    finalized = assignment.get('submissionsFinalizedCount') or 0

    plan = {
        'assignment': {'id': assignment.get('id'), 'name': assignment.get('name')},
        'from': current_wire, 'to': target_wire,
        'submissions': {'total': total, 'finalized': finalized,
                        'unfinalized': total - finalized},
        'warnings': [],
        'sideEffects': [],
    }
    if target_wire == 'released':
        plan['sideEffects'].append(
            'feedbackReleasedAt will be stamped — it anchors any quiz close '
            'events tied to feedback release.')
        if total and finalized < total:
            plan['warnings'].append(
                f'{total - finalized} of {total} submissions are not finalized; '
                f"those students will see nothing. Consider 'perStudent' for a "
                'rolling release.')
    revoking = (current_wire == 'released' and target_wire != 'released')
    if revoking:
        plan['warnings'].append(
            'Students who have already seen their grades will lose access; '
            'feedbackReleasedAt is cleared, un-anchoring quiz close events.')

    args = {'assignmentId': assignmentId, 'targetStage': targetStage,
            'hideGrades': hideGrades, 'scheduleAt': scheduleAt}

    if dryRun:
        if revoking:
            raise guardrails.confirmation_required(
                'codepost_set_feedback_stage', args, plan,
                course_id=ctx.course.id, user_id=ctx.user.pk,
                message='Revoking released feedback is disruptive. Review the '
                        'plan with the user, then confirm.')
        return shaping.envelope(
            {'course': course_header(ctx.course), 'plan': plan},
            meta={'dryRun': True, 'hint': 'Re-call with dryRun=false to apply.'})

    if revoking:
        guardrails.verify_token(confirmToken, 'codepost_set_feedback_stage',
                                args, plan, course_id=ctx.course.id,
                                user_id=ctx.user.pk)

    body = {'feedbackStatus': target_wire}
    if hideGrades is not None:
        body['hideGrades'] = hideGrades
    if scheduleAt:
        body['releaseFeedbackAt'] = scheduleAt
    data = ctx.dispatch.require(
        AssignmentViewSet, {'patch': 'partial_update'},
        method='PATCH', path=f'/assignments/{assignmentId}/', data=body,
        pk=assignmentId, what=f'setting feedback stage on assignment {assignmentId}')

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course), 'changed': True,
         'from': current_wire, 'to': data.get('feedbackStatus'),
         'hideGrades': data.get('hideGrades')},
        warnings=plan['warnings'] or None))
