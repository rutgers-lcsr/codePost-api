# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import string

from rest_framework import serializers

from core.prompts.registry import prompt_registry


def validate_prompt_placeholders(template, prompt_type, field='text'):
    """Reject a prompt template whose ``{placeholders}`` are malformed or outside the
    prompt type's allowed set. An unknown type has an empty allowed set, so any
    placeholder in it is rejected. Raises ``ValidationError({field: ...})``."""
    if not template:
        return
    allowed = prompt_registry.get_allowed_placeholders(prompt_type)
    used = set()
    try:
        for _, field_name, _, _ in string.Formatter().parse(template):
            if field_name is not None:
                # Handle nested access like {foo.bar} — only validate the root name
                root = field_name.split('.')[0].split('[')[0]
                if root:
                    used.add(root)
    except (ValueError, KeyError):
        raise serializers.ValidationError({
            field: 'Invalid template syntax. Check for unmatched or malformed {placeholders}.'
        })
    invalid = used - allowed
    if invalid:
        raise serializers.ValidationError({
            field: (
                f"Unknown placeholder(s): {{{', '.join(sorted(invalid))}}}. "
                f"Allowed placeholders for {prompt_type}: {{{', '.join(sorted(allowed))}}}."
            )
        })
