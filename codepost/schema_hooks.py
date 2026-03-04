# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Postprocessing hooks for drf-spectacular schema generation.

These hooks run after the schema is generated but before it is serialized,
allowing us to fix operationIds for compatibility with openapi-generator's
removeOperationIdPrefix option.
"""
import re


def _camelize_tag(tag: str) -> str:
    """
    Convert a dashed tag name to camelCase to match how drf-spectacular
    camelizes operationIds.

    e.g. 'tmp-script' -> 'tmpScript'
         'token-auth' -> 'tokenAuth'
         'assignments' -> 'assignments'
    """
    parts = tag.split('-')
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])


def restore_underscore_operation_ids(result, generator, **kwargs):
    """
    Post-processing hook for drf-spectacular.

    When CAMELIZE_NAMES=True, drf-spectacular camelizes operationIds,
    removing the underscore between the tag prefix and action:
      courses_list -> coursesList
      tmp_script_create -> tmpScriptCreate

    This breaks openapi-generator's removeOperationIdPrefix option, which
    requires an underscore separator to identify the prefix.

    This hook restores the underscore separator in all operationIds:
      coursesList -> courses_list
      tmpScriptCreate -> tmpScript_create
    """
    paths = result.get('paths', {})
    for path_key, path_item in paths.items():
        for method in ('get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'):
            operation = path_item.get(method)
            if operation and 'operationId' in operation:
                old_id = operation['operationId']
                tags = operation.get('tags', [])
                if tags:
                    tag = tags[0]
                    # The tag may contain dashes (e.g. 'tmp-script') while
                    # the operationId is fully camelized ('tmpScriptCreate').
                    # Convert the tag to camelCase to find it in the operationId.
                    camel_tag = _camelize_tag(tag)
                    if old_id.startswith(camel_tag) and len(old_id) > len(camel_tag):
                        next_char = old_id[len(camel_tag)]
                        if next_char.isupper():
                            new_id = camel_tag + '_' + next_char.lower() + old_id[len(camel_tag)+1:]
                            operation['operationId'] = new_id
    return result
