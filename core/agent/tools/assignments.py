# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Assignment read tools."""
from __future__ import annotations

from core.agent import errors, shaping
from core.agent.registry import SCOPE_READ, tool
from core.agent.tools._common import (ASSIGNMENT_COUNT_FIELDS,
                                      ASSIGNMENT_SUMMARY_FIELDS, course_header,
                                      fetch_assignment, load_assignments)
from core.permissions.capabilities import Capability

# Group selector for get_assignment. The full staff serializer is ~35 fields;
# defaulting to all of them wastes context on almost every call.
_INCLUDE_GROUPS = {
    'lifecycle': ('state', 'effectiveState', 'feedbackStatus', 'hideGrades',
                  'publishAt', 'publishedAt', 'releaseFeedbackAt', 'isVisible',
                  'isReleased', 'feedbackReleased', 'liveFeedbackMode'),
    'counts': ASSIGNMENT_COUNT_FIELDS + ('statsMax', 'statsMin', 'statsMean'),
    'settings': ('allowStudentUpload', 'allowStudentUploadWithPartners',
                 'allowLateUploads', 'maxLateDays', 'lateDeductions',
                 'uploadDueDate', 'anonymousGrading', 'additiveGrading',
                 'allowRegradeRequests', 'regradeDeadline', 'regradeInstructions',
                 'forcedRubricMode', 'gradersCanEditSubmissions',
                 'studentsCanSeeGraders', 'runTestsOnSubmit', 'testsAffectGrade',
                 'maxStudentTestRuns', 'hideFrom', 'explanation'),
    'rubric': ('rubricCategories',),
    'autograder': ('environment', 'testCategories'),
}


@tool(
    name='codepost_get_assignment',
    title='Assignment detail',
    description=(
        'Full detail for one assignment. Use the include argument to pick what '
        'you need — the settings group alone is about 35 fields.\n\n'
        'Get assignmentId from codepost_get_course_overview.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'assignmentId': {'type': 'integer'},
            'include': {
                'type': 'array',
                'items': {'enum': ['lifecycle', 'counts', 'settings', 'rubric',
                                   'autograder']},
                'description': "Defaults to ['lifecycle', 'counts'].",
            },
        },
        'required': ['assignmentId'],
        'additionalProperties': False,
    },
    capability=Capability.VIEW_COURSE,
    min_scope=SCOPE_READ,
    read_only=True,
)
def get_assignment(ctx, assignmentId: int, include=None):
    data = fetch_assignment(ctx, assignmentId)
    groups = include or ['lifecycle', 'counts']

    fields = set(('id', 'name', 'points'))
    for group in groups:
        fields.update(_INCLUDE_GROUPS.get(group, ()))

    payload = shaping.envelope(
        {'course': course_header(ctx.course),
         'assignment': shaping.project(data, fields)},
        meta={'included': groups})
    return shaping.enforce_budget(payload)


@tool(
    name='codepost_get_grading_progress',
    title='Grading progress',
    description=(
        'How far along grading is for one assignment: how many submissions are '
        'finalized, still in progress, unclaimed, and how many students have '
        'not submitted at all — plus a per-grader breakdown.\n\n'
        'Returns counts only, never submission rows. Use this before '
        'codepost_list_submissions; on a large course the row list is enormous '
        'and rarely what you actually need.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'assignmentId': {'type': 'integer'},
            'byGrader': {'type': 'boolean', 'default': True},
        },
        'required': ['assignmentId'],
        'additionalProperties': False,
    },
    capability=Capability.VIEW_ANALYTICS,
    min_scope=SCOPE_READ,
    read_only=True,
)
def get_grading_progress(ctx, assignmentId: int, byGrader: bool = True):
    from core.views.assignment import AssignmentViewSet

    assignment = fetch_assignment(ctx, assignmentId)

    total = assignment.get('submissionsCount') or 0
    finalized = assignment.get('submissionsFinalizedCount') or 0
    in_progress = assignment.get('submissionsInprogressCount') or 0

    submissions = {
        'total': total,
        'finalized': finalized,
        'inProgress': in_progress,
        'unclaimed': assignment.get('submissionsUnclaimedCount') or 0,
        'missingStudents': assignment.get('submissionsMissingCount') or 0,
        'percentFinalized': round(100.0 * finalized / total, 1) if total else None,
    }

    data = {
        'course': course_header(ctx.course),
        'assignment': shaping.project(assignment, ASSIGNMENT_SUMMARY_FIELDS),
        'submissions': submissions,
        'grades': {
            'mean': assignment.get('statsMean'),
            'min': assignment.get('statsMin'),
            'max': assignment.get('statsMax'),
        },
    }

    if byGrader:
        # graderWorkload is the course-wide view; queueLength's finalized and
        # unfinalized counts filter on grader=request.user, which is the key's
        # service account, so they always read zero here.
        analytics = ctx.dispatch.call(
            AssignmentViewSet, {'get': 'analytics'},
            method='GET', path=f'/assignments/{assignmentId}/analytics/',
            pk=assignmentId)
        if analytics.ok and isinstance(analytics.data, dict):
            data['byGrader'] = analytics.data.get('graderWorkload') or []
        else:
            data['byGrader'] = []
            data['byGraderUnavailable'] = True

    blockers = []
    if submissions['inProgress']:
        blockers.append({
            'kind': 'unfinalized', 'count': submissions['inProgress'],
            'hint': f'codepost_list_submissions(assignmentId={assignmentId}, '
                    f'status="unfinalized")'})
    if submissions['unclaimed']:
        blockers.append({
            'kind': 'unclaimed', 'count': submissions['unclaimed'],
            'hint': f'codepost_list_submissions(assignmentId={assignmentId}, '
                    f'status="unclaimed")'})
    if submissions['missingStudents']:
        blockers.append({
            'kind': 'missing', 'count': submissions['missingStudents'],
            'hint': f'codepost_list_submissions(assignmentId={assignmentId}, '
                    f'status="missing")'})
    data['blockers'] = blockers

    return shaping.enforce_budget(shaping.envelope(data))


@tool(
    name='codepost_get_rubric',
    title='Assignment rubric',
    description=(
        'The rubric for one assignment: categories with point limits, and every '
        'rubric comment with its point delta. The ids returned here are what '
        'rubric-editing tools take.'
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
    min_scope=SCOPE_READ,
    read_only=True,
)
def get_rubric(ctx, assignmentId: int):
    from core.views.assignment import AssignmentViewSet

    assignment = fetch_assignment(ctx, assignmentId)
    data = ctx.dispatch.require(
        AssignmentViewSet, {'get': 'rubric'},
        method='GET', path=f'/assignments/{assignmentId}/rubric/', pk=assignmentId,
        what=f'reading the rubric for assignment {assignmentId}')

    categories = [shaping.project(c, ('id', 'name', 'pointLimit', 'sortKey',
                                      'helpText', 'atMostOnce'))
                  for c in (data.get('rubricCategories') or [])]
    comments = [shaping.project(c, ('id', 'category', 'text', 'pointDelta',
                                    'explanation', 'sortKey'))
                for c in (data.get('rubricComments') or [])]

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course),
         'assignment': {'id': assignment.get('id'), 'name': assignment.get('name'),
                        'points': assignment.get('points')},
         'rubricCategories': categories,
         'rubricComments': comments},
        meta={'categories': len(categories), 'comments': len(comments)}))
