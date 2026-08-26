# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Assignment content and autograder setup.

Three well-documented traps this module is built around (see the plan):

1. Saving an ``AssignmentFile`` queues auto-detection, which may create an
   Environment, flip its language, and start a Docker rebuild — silently.
2. Writing ``TestCategory.testScript`` synchronously creates/updates/DELETES
   ``TestCase`` rows keyed by ``functionName``; a broken script leaves stale
   tests in place without erroring.
3. ``PATCH environments/{id}`` with ``autoDetect: true`` wipes hand-written
   dockerfile and requirements — no tool here ever sends that flag.
"""
from __future__ import annotations

from core.agent import errors, guardrails, shaping
from core.agent.registry import SCOPE_WRITE, tool
from core.agent.tools._common import course_header, fetch_assignment
from core.permissions.capabilities import Capability

# Keep well under Django's 2.5MB request-body cap; anything bigger than this is
# not something an agent should be writing inline anyway.
_MAX_CONTENT_CHARS = 1_000_000


@tool(
    name='codepost_manage_assignment_files',
    title='Assignment files',
    description=(
        'The files students receive with an assignment — the spec, starter '
        'code, and hidden helpers. Text content only (UTF-8).\n\n'
        "op='list' shows the files. op='get' returns one file's content. "
        "op='add' creates one; op='update' changes "
        "content or flags; op='remove' deletes one. Flags: required=true means "
        'students MUST include a file with this name in their submission; '
        'hidden=true hides it from students (available to tests).\n\n'
        'Adding or changing files may trigger autograder environment '
        're-detection and a Docker rebuild if the environment is in auto-detect '
        'mode — the result will say when that applies.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'assignmentId': {'type': 'integer'},
            'op': {'enum': ['list', 'get', 'add', 'update', 'remove'],
                   'default': 'list'},
            'fileId': {'type': 'integer',
                       'description': "For get/update/remove (from op='list')."},
            'name': {'type': 'string',
                     'description': "Filename with extension, e.g. 'hw3.py'."},
            'content': {'type': 'string',
                        'description': 'UTF-8 text content (max ~1MB).'},
            'path': {'type': 'string',
                     'description': 'Optional slash-delimited directory.'},
            'required': {'type': 'boolean'},
            'hidden': {'type': 'boolean'},
            'description': {'type': 'string',
                            'description': 'Shown to students beside the file.'},
        },
        'required': ['assignmentId'],
        'additionalProperties': False,
    },
    capability=Capability.CREATE_ASSIGNMENT,
    min_scope=SCOPE_WRITE, tier=1,
    read_only=False, destructive=False, idempotent=False,
)
def manage_assignment_files(ctx, assignmentId: int, op: str = 'list', fileId=None,
                            name: str = '', content: str = '', path: str = '',
                            required=None, hidden=None, description: str = ''):
    from core.views.assignmentFile import AssignmentFileViewSet

    assignment = fetch_assignment(ctx, assignmentId)

    if op == 'list':
        rows = []
        for fid in (assignment.get('files') or []):
            result = ctx.dispatch.call(
                AssignmentFileViewSet, {'get': 'retrieve'},
                method='GET', path=f'/assignmentFiles/{fid}/', pk=fid)
            if result.ok:
                rows.append(shaping.project(result.data, (
                    'id', 'name', 'extension', 'path', 'required', 'hidden',
                    'isTestResource', 'description')))
        return shaping.enforce_budget(shaping.envelope(
            {'course': course_header(ctx.course),
             'assignment': {'id': assignment.get('id'),
                            'name': assignment.get('name')},
             'files': rows},
            meta={'total': len(rows)},
            warnings=["File contents are not listed — read one with "
                      "op='get', fileId=…."]))

    if op == 'get':
        if fileId is None:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET', "op='get' needs a fileId.",
                remedy="Get ids from op='list'.", retryable=True)
        data = ctx.dispatch.require(
            AssignmentFileViewSet, {'get': 'retrieve'},
            method='GET', path=f'/assignmentFiles/{fileId}/', pk=fileId,
            what=f'reading assignment file {fileId}')
        content = data.get('data') or ''
        truncated = len(content) > _MAX_CONTENT_CHARS
        payload = shaping.project(data, ('id', 'name', 'extension', 'path',
                                         'required', 'hidden', 'description'))
        payload['content'] = content[:_MAX_CONTENT_CHARS]
        return shaping.enforce_budget(shaping.envelope(
            {'course': course_header(ctx.course),
             'assignment': {'id': assignment.get('id'),
                            'name': assignment.get('name')},
             'file': payload},
            warnings=([f'Content truncated to {_MAX_CONTENT_CHARS // 1000}KB.']
                      if truncated else None)))

    if op == 'remove':
        if fileId is None:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET', "op='remove' needs a fileId.",
                remedy="Get ids from op='list'.", retryable=True)
        ctx.dispatch.require(
            AssignmentFileViewSet, {'delete': 'destroy'},
            method='DELETE', path=f'/assignmentFiles/{fileId}/', pk=fileId,
            what=f'removing assignment file {fileId}')
        return shaping.envelope(
            {'course': course_header(ctx.course), 'removed': fileId},
            warnings=_autodetect_warning(ctx, assignment))

    # add / update
    if len(content or '') > _MAX_CONTENT_CHARS:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET',
            f'content exceeds the {_MAX_CONTENT_CHARS // 1000}KB tool limit.',
            remedy='Upload very large files through the codePost UI instead.')

    warnings = []
    if (name or '').endswith('.ipynb'):
        warnings.append('Notebook files are rewritten server-side (cell ids '
                        'injected, JSON reformatted) — the stored bytes will '
                        'differ from what was sent.')

    if op == 'add':
        if not name or not content:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET', "op='add' needs name and content.",
                remedy='Provide both.', retryable=True)
        # The serializer requires an explicit extension; derive it from the
        # filename so the model never has to name it separately.
        body = {'assignment': assignmentId, 'name': name, 'data': content,
                'extension': _extension_of(name)}
        if path:
            body['path'] = path
        if required is not None:
            body['required'] = required
        if hidden is not None:
            body['hidden'] = hidden
        if description:
            body['description'] = description
        data = ctx.dispatch.require(
            AssignmentFileViewSet, {'post': 'create'},
            method='POST', path='/assignmentFiles/', data=body,
            what=f"adding file '{name}'")
    else:  # update
        if fileId is None:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET', "op='update' needs a fileId.",
                remedy="Get ids from op='list'.", retryable=True)
        body = {}
        for key, value in (('name', name or None), ('data', content or None),
                           ('path', path or None), ('required', required),
                           ('hidden', hidden),
                           ('description', description or None)):
            if value is not None:
                body[key] = value
        if not body:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET', 'Nothing to change.',
                remedy='Pass at least one field.', retryable=True)
        data = ctx.dispatch.require(
            AssignmentFileViewSet, {'patch': 'partial_update'},
            method='PATCH', path=f'/assignmentFiles/{fileId}/', data=body,
            pk=fileId, what=f'updating assignment file {fileId}')

    if required:
        warnings.append("This file is 'required': students must now include a "
                        'file with this exact name in their submissions.')
    warnings.extend(_autodetect_warning(ctx, assignment) or [])

    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course),
         'file': shaping.project(data, ('id', 'name', 'extension', 'path',
                                        'required', 'hidden', 'description'))},
        warnings=warnings or None))


def _extension_of(name: str) -> str:
    dot = name.rfind('.')
    return name[dot:] if dot > 0 else ''


def _autodetect_warning(ctx, assignment):
    """Warn when a file change can silently rebuild the autograder image."""
    from autograder.views.environment import EnvironmentViewSet

    env_id = assignment.get('environment')
    if not env_id:
        return ['No autograder environment exists yet; this file change may '
                'auto-create one via language detection.']
    env = ctx.dispatch.call(
        EnvironmentViewSet, {'get': 'retrieve'},
        method='GET', path=f'/autograder/environments/{env_id}/', pk=env_id)
    if env.ok and env.data.get('autoDetect'):
        return ['The autograder environment is in auto-detect mode: this file '
                'change queues re-detection and may rebuild the Docker image. '
                "Check codepost_run_autograder(op='status') afterwards."]
    return None


@tool(
    name='codepost_manage_test_cases',
    title='Autograder test script',
    description=(
        "Author an assignment's autograder tests as a script of @test-decorated "
        'functions.\n\n'
        "ALWAYS start with op='preview': it parses the script WITHOUT saving "
        'and shows exactly which tests would exist, with points. Then '
        "op='setScript' saves it — which synchronously creates/updates the "
        'test cases AND DELETES any existing test case whose function is no '
        "longer in the script (the result names them first). op='sync' "
        're-runs the script→tests sync as a repair.\n\n'
        'Decorators: @test("Title", points) or keywords points=, timeout=, '
        'hidden=, description=.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'assignmentId': {'type': 'integer'},
            'op': {'enum': ['preview', 'setScript', 'sync'],
                   'default': 'preview'},
            'testScript': {'type': 'string',
                           'description': 'The @test-decorated script.'},
            'categoryName': {'type': 'string', 'maxLength': 48,
                             'description': "Test category (created if new). "
                                            "Defaults to 'Autograder'."},
            'categoryId': {'type': 'integer',
                           'description': 'Alternative to categoryName for '
                                          'existing categories.'},
            'targetFileName': {'type': 'string',
                               'description': 'The student file the tests run '
                                              'against.'},
            'language': {'type': 'string', 'default': 'python',
                         'description': 'For preview parsing.'},
        },
        'required': ['assignmentId'],
        'additionalProperties': False,
    },
    capability=Capability.CREATE_ASSIGNMENT,
    min_scope=SCOPE_WRITE, tier=1,
    read_only=False, destructive=True, idempotent=False,
)
def manage_test_cases(ctx, assignmentId: int, op: str = 'preview',
                      testScript: str = '', categoryName: str = '',
                      categoryId=None, targetFileName: str = '',
                      language: str = 'python'):
    from core.views.testCategory import TestCategoryViewSet

    assignment = fetch_assignment(ctx, assignmentId)

    if op == 'preview':
        if not testScript:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET', "op='preview' needs a testScript.",
                remedy='Provide the script to parse.', retryable=True)
        parsed = ctx.dispatch.require(
            TestCategoryViewSet, {'post': 'preview_script'},
            method='POST', path='/testCategories/preview-script/',
            data={'testScript': testScript, 'language': language},
            what='previewing the test script')
        tests = parsed if isinstance(parsed, list) else []
        return shaping.enforce_budget(shaping.envelope(
            {'course': course_header(ctx.course),
             'parsedTests': tests,
             'totalPoints': sum(float(t.get('points') or 0) for t in tests)},
            meta={'count': len(tests),
                  'hint': "Looks right? Save with op='setScript'."},
            warnings=(['The script parsed to ZERO tests — saving it would '
                       'leave existing tests untouched but add nothing. Check '
                       'the @test decorators and language.'] if not tests
                      else None)))

    if op == 'sync':
        if categoryId is None:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET', "op='sync' needs a categoryId.",
                remedy='Find it via codepost_get_assignment '
                       "include=['autograder'].", retryable=True)
        result = ctx.dispatch.require(
            TestCategoryViewSet, {'post': 'sync_tests'},
            method='POST', path=f'/testCategories/{categoryId}/sync-tests/',
            pk=categoryId, what=f'syncing tests for category {categoryId}')
        return shaping.envelope(
            {'course': course_header(ctx.course), 'sync': result},
            warnings=['Sync deletes test cases whose functions are no longer '
                      'in the script.'])

    # op == 'setScript'
    if not testScript:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET', "op='setScript' needs a testScript.",
            remedy="Preview it first with op='preview'.", retryable=True)

    # Parse first so the destructive diff can be reported honestly.
    parsed = ctx.dispatch.require(
        TestCategoryViewSet, {'post': 'preview_script'},
        method='POST', path='/testCategories/preview-script/',
        data={'testScript': testScript, 'language': language},
        what='validating the test script')
    parsed_names = {t.get('functionName') for t in (parsed or [])}
    if not parsed_names:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET',
            'The script parses to zero tests; saving would do nothing useful.',
            remedy="Fix the @test decorators (preview with op='preview') and "
                   'try again.', retryable=True)

    category, removed = _find_or_create_category(
        ctx, assignment, categoryId, categoryName or 'Autograder',
        targetFileName, parsed_names)

    ctx.dispatch.require(
        TestCategoryViewSet, {'patch': 'partial_update'},
        method='PATCH', path=f'/testCategories/{category["id"]}/',
        data={'testScript': testScript,
              **({'targetFileName': targetFileName} if targetFileName else {})},
        pk=category['id'], what='saving the test script')

    # The script→tests sync recomputes maxPoints (and the case list) AFTER the
    # PATCH response serialises, so re-read for the true stored state.
    data = ctx.dispatch.require(
        TestCategoryViewSet, {'get': 'retrieve'},
        method='GET', path=f'/testCategories/{category["id"]}/',
        pk=category['id'], what='re-reading the test category')

    warnings = []
    if removed:
        warnings.append(f'These existing tests were REMOVED because their '
                        f'functions left the script: {sorted(removed)}')
    return shaping.enforce_budget(shaping.envelope(
        {'course': course_header(ctx.course),
         'category': {'id': data.get('id'), 'name': data.get('name'),
                      'maxPoints': data.get('maxPoints'),
                      'testCases': len(data.get('testCases') or [])},
         'tests': [{'functionName': t.get('functionName'),
                    'name': t.get('name'), 'points': t.get('points')}
                   for t in (parsed or [])]},
        warnings=warnings or None))


def _find_or_create_category(ctx, assignment, category_id, name,
                             target_file_name, parsed_names):
    """Resolve the target TestCategory; returns (category, removedFunctionNames)."""
    from core.views.testCategory import TestCategoryViewSet

    if category_id is not None:
        existing = ctx.dispatch.require(
            TestCategoryViewSet, {'get': 'retrieve'},
            method='GET', path=f'/testCategories/{category_id}/', pk=category_id,
            what=f'reading test category {category_id}')
        removed = _removed_functions(ctx, existing, parsed_names)
        return existing, removed

    # By name: look through the assignment's existing categories.
    for cid in (assignment.get('testCategories') or []):
        result = ctx.dispatch.call(
            TestCategoryViewSet, {'get': 'retrieve'},
            method='GET', path=f'/testCategories/{cid}/', pk=cid)
        if result.ok and result.data.get('name') == name:
            removed = _removed_functions(ctx, result.data, parsed_names)
            return result.data, removed

    created = ctx.dispatch.require(
        TestCategoryViewSet, {'post': 'create'},
        method='POST', path='/testCategories/',
        data={'assignment': assignment['id'], 'name': name,
              **({'targetFileName': target_file_name} if target_file_name else {})},
        what=f"creating test category '{name}'")
    return created, set()


def _removed_functions(ctx, category, parsed_names):
    """Which existing test functions would the new script delete?"""
    from core.views.testCase import TestCaseViewSet

    removed = set()
    for tid in (category.get('testCases') or []):
        result = ctx.dispatch.call(
            TestCaseViewSet, {'get': 'retrieve'},
            method='GET', path=f'/testCases/{tid}/', pk=tid)
        if result.ok:
            fn = result.data.get('functionName')
            if fn and fn not in parsed_names:
                removed.add(fn)
    return removed


@tool(
    name='codepost_run_autograder',
    title='Autograder build & run',
    description=(
        "Build and run the assignment's autograder.\n\n"
        "op='status' shows the environment (language, build state, logs tail). "
        "op='build' (re)builds the Docker image — returns a job for "
        "codepost_poll_job. op='runOne' runs the tests on one submission. "
        "op='runAll' re-runs tests on EVERY submission (preview first; sending "
        'email to students requires explicitly setting sendEmail=true).'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'assignmentId': {'type': 'integer'},
            'op': {'enum': ['status', 'build', 'runOne', 'runAll'],
                   'default': 'status'},
            'submissionId': {'type': 'integer',
                             'description': "For op='runOne'."},
            'sendEmail': {'type': 'boolean', 'default': False,
                          'description': 'runAll only: email every student '
                                         'their results. A real email blast — '
                                         'leave false unless the user asked.'},
            'confirmToken': {'type': 'string',
                             'description': 'runAll only: the token from the '
                                            'preview this tool returns first.'},
        },
        'required': ['assignmentId'],
        'additionalProperties': False,
    },
    capability=Capability.CREATE_ASSIGNMENT,
    min_scope=SCOPE_WRITE, tier=2,
    read_only=False, destructive=False, idempotent=False,
)
def run_autograder(ctx, assignmentId: int, op: str = 'status', submissionId=None,
                   sendEmail: bool = False, confirmToken: str = ''):
    from autograder.views.environment import EnvironmentViewSet

    assignment = fetch_assignment(ctx, assignmentId)
    env_id = assignment.get('environment')

    if env_id is None:
        raise errors.ToolError(
            'PRECONDITION_NOT_MET',
            'This assignment has no autograder environment yet.',
            remedy='Add an assignment file (auto-detection creates one), or '
                   'set the environment up in the codePost UI first.')

    if op == 'status':
        env = ctx.dispatch.require(
            EnvironmentViewSet, {'get': 'retrieve'},
            method='GET', path=f'/autograder/environments/{env_id}/', pk=env_id,
            what='reading the environment')
        logs = env.get('buildLogs') or ''
        return shaping.enforce_budget(shaping.envelope(
            {'course': course_header(ctx.course),
             'assignment': {'id': assignmentId, 'name': assignment.get('name')},
             'environment': {
                 'id': env_id,
                 'language': env.get('language'),
                 'autoDetect': env.get('autoDetect'),
                 # 0 Not Built, 1 Building, 2 Success, 3 Failed
                 'buildStatus': env.get('buildStatus'),
                 'buildStatusLabel': {0: 'notBuilt', 1: 'building',
                                      2: 'success', 3: 'failed'}.get(
                                          env.get('buildStatus'), 'unknown'),
                 'lastBuilt': env.get('lastBuilt'),
                 'buildLogsTail': ('…' + logs[-1500:]) if len(logs) > 1500 else logs,
             }}))

    if op == 'build':
        # Body deliberately empty: passing autoDetect would wipe hand-written
        # dockerfile/requirements, and language changes belong to the UI.
        result = ctx.dispatch.require(
            EnvironmentViewSet, {'patch': 'build'},
            method='PATCH', path=f'/autograder/environments/{env_id}/build/',
            data={}, pk=env_id, what='queueing the environment build')
        return shaping.envelope(
            {'course': course_header(ctx.course),
             'job': {'jobId': result.get('task'), 'jobType': 'environmentBuild',
                     'environmentId': env_id}},
            meta={'hint': 'Poll with codepost_poll_job(jobId=…, '
                          'jobType="environmentBuild") — pass the environmentId '
                          'as jobId.'})

    if op == 'runOne':
        if submissionId is None:
            raise errors.ToolError(
                'PRECONDITION_NOT_MET', "op='runOne' needs a submissionId.",
                remedy='Get one from codepost_list_submissions.', retryable=True)
        result = ctx.dispatch.require(
            EnvironmentViewSet, {'patch': 'run'},
            method='PATCH', path=f'/autograder/environments/{env_id}/run/',
            data={'submission': submissionId}, pk=env_id,
            what=f'running tests on submission {submissionId}')
        return shaping.envelope(
            {'course': course_header(ctx.course),
             'job': {'jobId': result.get('task'), 'jobType': 'autograderTask'}},
            meta={'hint': 'Poll with codepost_poll_job.'})

    # op == 'runAll'
    total = assignment.get('submissionsCount') or 0
    plan = {'assignment': {'id': assignmentId, 'name': assignment.get('name')},
            'submissions': total,
            'sendEmail': sendEmail,
            'testsAffectGrade': assignment.get('testsAffectGrade')}
    args = {'assignmentId': assignmentId, 'op': 'runAll', 'sendEmail': sendEmail}

    # No dryRun flag here: the first runAll call always returns the plan and a
    # token; only a call carrying that token executes.
    if not confirmToken:
        raise guardrails.confirmation_required(
            'codepost_run_autograder', args, plan,
            course_id=ctx.course.id, user_id=ctx.user.pk,
            message=(f'This re-runs the autograder on all {total} submissions'
                     + (' AND EMAILS EVERY STUDENT their results'
                        if sendEmail else '')
                     + ('; testsAffectGrade is on, so grades may change.'
                        if assignment.get('testsAffectGrade') else '.')))

    guardrails.verify_token(confirmToken, 'codepost_run_autograder', args, plan,
                            course_id=ctx.course.id, user_id=ctx.user.pk)
    result = ctx.dispatch.require(
        EnvironmentViewSet, {'patch': 'runAll'},
        method='PATCH', path=f'/autograder/environments/{env_id}/runAll/',
        data={'sendEmail': sendEmail}, pk=env_id,
        what='running the autograder on all submissions')
    return shaping.envelope(
        {'course': course_header(ctx.course),
         'job': {'jobId': result.get('task'), 'jobType': 'autograderTask'},
         'submissions': total, 'emailed': sendEmail},
        meta={'hint': 'Poll with codepost_poll_job.'})
