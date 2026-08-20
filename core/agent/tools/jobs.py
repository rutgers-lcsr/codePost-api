# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Background-job polling — one shape over the API's several job endpoints."""
from __future__ import annotations

from core.agent import shaping
from core.agent.registry import SCOPE_READ, tool
from core.agent.tools._common import course_header

# Normalised terminal states, whatever the underlying endpoint calls them.
_TERMINAL_OK = {'SUCCESS', 'completed', 'succeeded', 'built'}
_TERMINAL_BAD = {'FAILURE', 'failed', 'error', 'REVOKED'}
_LOG_CAP = 2000  # build transcripts run to many KB; keep the tail only


@tool(
    name='codepost_poll_job',
    title='Check a background job',
    description=(
        'Check on a background job started by another tool (autograder runs, '
        'quiz imports, AI question generation). Returns one normalised shape: '
        "state is 'pending', 'succeeded' or 'failed'. Poll every few seconds "
        'while pending; stop on any other state.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'jobId': {'type': 'string'},
            'jobType': {'enum': ['autograderTask', 'quizSuggestion', 'quizImport',
                                 'environmentBuild'],
                        'description': 'Returned alongside jobId by the tool that '
                                       'started the job.'},
        },
        'required': ['jobId', 'jobType'],
        'additionalProperties': False,
    },
    min_scope=SCOPE_READ,
    read_only=True,
    # Poll results change between calls by design.
    idempotent=False,
)
def poll_job(ctx, jobId: str, jobType: str):
    if jobType == 'autograderTask':
        raw = _poll_autograder(ctx, jobId)
    elif jobType == 'environmentBuild':
        raw = _poll_build(ctx, jobId)
    elif jobType == 'quizSuggestion':
        raw = _poll_viewset(ctx, jobId, 'quizSuggestionJobs',
                            'core.views.quizSuggestionJob', 'QuizSuggestionJobViewSet')
    else:
        raw = _poll_viewset(ctx, jobId, 'quizImportJobs',
                            'core.views.quizImportJob', 'QuizImportJobViewSet')

    status = str(raw.get('status', 'PENDING'))
    if status in _TERMINAL_OK:
        state = 'succeeded'
    elif status in _TERMINAL_BAD:
        state = 'failed'
    else:
        state = 'pending'

    result = raw.get('result') or raw.get('error') or raw.get('progress')
    if isinstance(result, str) and len(result) > _LOG_CAP:
        result = '…' + result[-_LOG_CAP:]

    payload = {'course': course_header(ctx.course) if ctx.course else None,
               'jobId': jobId, 'jobType': jobType,
               'state': state, 'rawStatus': status, 'result': result}
    meta = {}
    if state == 'pending':
        meta['hint'] = 'Still running. Poll again in a few seconds.'
    return shaping.enforce_budget(shaping.envelope(payload, meta=meta))


def _poll_build(ctx, environment_id: str) -> dict:
    """jobId is the ENVIRONMENT id here — build state lives on the environment.

    build_status returns 500-with-a-body on internal errors; that is a
    'failed with info' answer, not a transport failure, so use call() and
    read whatever came back.
    """
    from autograder.views.environment import EnvironmentViewSet

    result = ctx.dispatch.call(
        EnvironmentViewSet, {'get': 'build_status'},
        method='GET',
        path=f'/autograder/environments/{environment_id}/build_status/',
        pk=environment_id)
    data = result.data if isinstance(result.data, dict) else {}
    if data.get('inProgress'):
        status = 'PENDING'
    elif data.get('isSuccess'):
        status = 'SUCCESS'
    else:
        status = 'FAILURE'
    logs = data.get('logs') or data.get('error') or ''
    return {'status': status, 'result': logs}


def _poll_autograder(ctx, job_id: str) -> dict:
    from autograder.views.TaskViewset import TaskViewSet

    return ctx.dispatch.require(
        TaskViewSet, {'get': 'retrieve'},
        method='GET', path=f'/autograder/tasks/{job_id}/', pk=job_id,
        what=f'polling task {job_id}') or {}


def _poll_viewset(ctx, job_id: str, prefix: str, module: str, cls_name: str) -> dict:
    from importlib import import_module

    view_cls = getattr(import_module(module), cls_name)
    return ctx.dispatch.require(
        view_cls, {'get': 'retrieve'},
        method='GET', path=f'/{prefix}/{job_id}/', pk=job_id,
        what=f'polling {prefix} job {job_id}') or {}
