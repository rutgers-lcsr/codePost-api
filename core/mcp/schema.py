# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""ToolSpec -> MCP tool descriptor."""
from __future__ import annotations

from core.agent.registry import ToolSpec


def to_mcp_tool(spec: ToolSpec, *, inject_course_id: bool = False) -> dict:
    """Render one tool for ``tools/list``.

    The annotations are advisory — the spec says clients must treat them as
    untrusted — so they drive client-side approval dialogs but are never the
    enforcement. Real enforcement is the key scope filter in
    ``registry.visible_tools`` plus the permission classes behind every
    dispatched call.
    """
    input_schema = spec.input_schema
    if inject_course_id:
        # Personal-token connections carry no course in the credential, so the
        # course is an explicit argument on every course-bound tool. Injected at
        # render time only — pinned (course-key) connections never see it, so
        # neither surface has conditional arguments.
        input_schema = {
            **input_schema,
            'properties': {
                'courseId': {
                    'type': 'integer',
                    'description': ('The course to act on. Get it from '
                                    'codepost_list_courses.'),
                },
                **input_schema.get('properties', {}),
            },
            'required': ['courseId'] + list(input_schema.get('required', [])),
        }

    descriptor = {
        'name': spec.name,
        'title': spec.title,
        'description': spec.description,
        'inputSchema': input_schema,
        'annotations': {
            'title': spec.title,
            'readOnlyHint': spec.read_only,
            'destructiveHint': spec.destructive,
            'idempotentHint': spec.idempotent,
            'openWorldHint': False,
        },
    }
    if spec.output_schema:
        descriptor['outputSchema'] = spec.output_schema
    return descriptor
