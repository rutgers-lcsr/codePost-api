# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The agent tool registry — transport-agnostic on purpose.

Nothing here knows about MCP.  ``core/mcp/`` is one adapter over this registry;
an in-app chat panel would be a second, mapping ``ToolSpec.input_schema``
(already JSON Schema) straight onto provider function declarations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from core.permissions.capabilities import Capability

# Key scopes, weakest first. A CourseAPIKey carries one of these; a tool is
# only advertised to a caller whose scope meets its `min_scope`.
SCOPE_READ = 'read'
SCOPE_WRITE = 'write'
SCOPE_ADMIN = 'admin'
SCOPE_ORDER = {SCOPE_READ: 0, SCOPE_WRITE: 1, SCOPE_ADMIN: 2}

# The capabilities `compute_course_capabilities` actually returns. A tool may
# only be gated on one of these; see ToolSpec.capability.
COURSE_LEVEL_CAPABILITIES = frozenset({
    Capability.VIEW_COURSE,
    Capability.EDIT_COURSE_SETTINGS,
    Capability.MANAGE_ROSTER,
    Capability.VIEW_ROSTER,
    Capability.MANAGE_SECTIONS,
    Capability.VIEW_ANALYTICS,
    Capability.CONFIGURE_AI,
    Capability.VIEW_AI_USAGE,
    Capability.CREATE_ASSIGNMENT,
    Capability.CLAIM_SUBMISSIONS,
    Capability.EDIT_RUBRIC,
    Capability.GRADE_QUIZ,
    Capability.MANAGE_REGRADES,
    Capability.VIEW_AUDIT_LOG,
    Capability.CHANGE_INVITE_CODE,
    Capability.MANAGE_COURSE_API_KEYS,
})


@dataclass(frozen=True)
class ToolSpec:
    name: str                       # "codepost_list_submissions" — codepost_ prefix is
                                    # required: MCP tool names share one flat namespace
                                    # across every server a client has connected.
    title: str                      # human label, shown in client approval dialogs
    description: str                # LLM-facing prose — this IS the API contract
    input_schema: dict
    handler: Callable[..., Any]
    output_schema: dict | None = None
    # Coarse gate, evaluated against the COURSE. Must be a course-level
    # capability — assignment/submission-level ones are not present in the
    # course capability map and would silently hide the tool. Per-object
    # permissions are enforced by the viewset each tool dispatches into.
    capability: Capability | None = None
    min_scope: str = SCOPE_READ
    tier: Literal[0, 1, 2, 3] = 0
    read_only: bool = True
    destructive: bool = False
    idempotent: bool = True
    # course_bound=False marks the rare tool that needs no course context
    # (codepost_list_courses). unscoped_only=True hides a tool from course-key
    # connections, where it would be meaningless.
    course_bound: bool = True
    unscoped_only: bool = False


_REGISTRY: dict[str, ToolSpec] = {}


def tool(**kwargs) -> Callable:
    """Register an agent tool.

    The handler signature is always ``(ctx: AgentContext, **validated_args)``.
    ``ctx`` carries the principal, the resolved course, and the Dispatcher;
    arguments arrive already validated against ``input_schema``.
    """
    def deco(fn):
        name = kwargs.get('name')
        if not name or not name.startswith('codepost_'):
            raise ValueError(f"agent tool name must start with 'codepost_': {name!r}")
        if name in _REGISTRY:
            raise ValueError(f'duplicate agent tool {name!r}')
        scope = kwargs.get('min_scope', SCOPE_READ)
        if scope not in SCOPE_ORDER:
            raise ValueError(f'unknown scope {scope!r} on {name!r}')
        if kwargs.get('read_only', True) and scope != SCOPE_READ:
            raise ValueError(f'{name!r} is read_only but requires scope {scope!r}')
        capability = kwargs.get('capability')
        if capability is not None and capability not in COURSE_LEVEL_CAPABILITIES:
            # Caught at import time rather than as a mysteriously missing tool:
            # visible_tools() evaluates this against the course, so an
            # assignment- or submission-level capability is never present and
            # would hide the tool from every caller.
            raise ValueError(
                f'{name!r} is gated on {capability!r}, which is not a course-level '
                f'capability. Gate on one of {sorted(c.value for c in COURSE_LEVEL_CAPABILITIES)}, '
                f'and let the dispatched viewset enforce per-object permissions.')
        _REGISTRY[name] = ToolSpec(handler=fn, **kwargs)
        return fn
    return deco


def get(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def all_tools() -> list[ToolSpec]:
    return sorted(_REGISTRY.values(), key=lambda s: s.name)


def scope_permits(actual: str, required: str) -> bool:
    return SCOPE_ORDER.get(actual, -1) >= SCOPE_ORDER[required]


def visible_tools(ctx) -> list[ToolSpec]:
    """The tools a course-key (pinned) principal may actually invoke.

    Filtering `tools/list` rather than only refusing at call time is the point
    of the scope system: a `write` key is never *told* that
    `codepost_delete_resource` exists, so the model cannot decide to try it.
    Hiding capability-denied tools also stops the model burning turns on
    guaranteed 403s.
    """
    from core.permissions.capabilities import check_capability

    out = []
    for spec in all_tools():
        if spec.unscoped_only:
            continue
        if not scope_permits(ctx.scope, spec.min_scope):
            continue
        if spec.capability and not check_capability(
                ctx.user, spec.capability, ctx.course, is_course_scoped=True):
            continue
        out.append(spec)
    return out


def visible_tools_unscoped(scope: str) -> list[ToolSpec]:
    """The tools advertised to a personal-token (unpinned) connection.

    There is no course yet, so the per-course capability filter cannot run at
    list time — only the scope filter applies here. Capability and permission
    enforcement happens per call, once a courseId argument names the course.
    """
    return [s for s in all_tools() if scope_permits(scope, s.min_scope)]


def load_tools() -> None:
    """Import every tool module so the decorators run. Idempotent."""
    from importlib import import_module
    for mod in ('course', 'assignments', 'grading', 'analytics', 'quizzes', 'jobs',
                'assignments_write', 'quizzes_write', 'attention', 'content_write',
                'people_write'):
        import_module(f'core.agent.tools.{mod}')
