# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Response shaping — the difference between a usable tool and a context blowup.

The raw API is built for a UI that renders what it fetches. An agent has a
fixed context window, so the governing rule here is: the caller opts in to
volume, and is always told what it did not get. Silent truncation is how an
agent concludes "only 25 students submitted".
"""
from __future__ import annotations

import base64
import json
from typing import Any, Iterable

# A tool result past this size crowds out the conversation it is meant to
# inform. Enforced last, after projection and paging have had their chance.
MAX_RESULT_CHARS = 8000

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def envelope(data: Any, *, meta: dict | None = None,
             warnings: list[str] | None = None) -> dict:
    """The one response shape every tool returns."""
    out: dict[str, Any] = {'data': data}
    out['meta'] = meta or {}
    if warnings:
        out['warnings'] = warnings
    return out


def project(row: dict, fields: Iterable[str]) -> dict:
    """Keep only ``fields``, silently skipping ones the row doesn't have."""
    wanted = set(fields)
    return {k: v for k, v in row.items() if k in wanted}


def clamp_limit(limit: Any) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(value, MAX_LIMIT))


def encode_cursor(payload: dict) -> str:
    """Opaque cursor, so the model never does pagination arithmetic itself."""
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode_cursor(cursor: str | None) -> dict:
    if not cursor:
        return {}
    try:
        padded = cursor + '=' * (-len(cursor) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:
        return {}


def paginate(rows: list, *, limit: int, offset: int = 0,
             cursor_payload: dict | None = None) -> tuple[list, dict]:
    """Slice ``rows`` and build the meta block describing what was left out."""
    total = len(rows)
    window = rows[offset:offset + limit]
    meta: dict[str, Any] = {
        'total': total,
        'returned': len(window),
        'truncated': offset + len(window) < total,
    }
    if meta['truncated']:
        meta['remaining'] = total - (offset + len(window))
        meta['cursor'] = encode_cursor({**(cursor_payload or {}),
                                        'offset': offset + len(window)})
        meta['hint'] = (f"{meta['remaining']} more rows. Re-call with this cursor to "
                        f'continue, or narrow the filters.')
    return window, meta


def enforce_budget(payload: dict) -> dict:
    """Last-resort trim so one tool result can't swallow the context window.

    Drops rows from the end of the longest list in ``data`` until the payload
    fits, and says so — never silently.
    """
    if _size(payload) <= MAX_RESULT_CHARS:
        return payload

    data = payload.get('data')
    target_key, target = _longest_list(data)
    if target_key is None:
        payload.setdefault('meta', {})['truncated'] = True
        payload['meta']['hint'] = (
            'Result exceeded the size budget and may be incomplete. '
            'Narrow the request.')
        return payload

    dropped = 0
    while target and _size(payload) > MAX_RESULT_CHARS:
        # Drop ~10% at a time; one-by-one is O(n) full re-serialisations.
        chunk = max(1, len(target) // 10)
        del target[-chunk:]
        dropped += chunk

    meta = payload.setdefault('meta', {})
    meta['truncated'] = True
    meta['droppedForSize'] = dropped
    meta['hint'] = (f'{dropped} rows were dropped to fit the response budget. '
                    f'Narrow the filters or lower `limit`, then call again.')
    return payload


def _size(payload: Any) -> int:
    return len(json.dumps(payload, default=str))


def _longest_list(data: Any) -> tuple[str | None, list | None]:
    if not isinstance(data, dict):
        return None, None
    best_key, best = None, None
    for key, value in data.items():
        if isinstance(value, list) and (best is None or len(value) > len(best)):
            best_key, best = key, value
    return best_key, best
