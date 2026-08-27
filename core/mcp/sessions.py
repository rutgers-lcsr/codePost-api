# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Session-lite registry for the MCP endpoint.

The endpoint stays stateless for every client that doesn't need more: no
session is created unless the client's ``initialize`` declares the
``elicitation`` capability, and a request without a session id behaves exactly
as before. A session exists for one purpose — remembering, across the
stateless calls that follow, that this client can show a human an
Approve/Decline dialog (used by Tier-3 confirmations).

State is IN-PROCESS ON PURPOSE. `/mcp` is served by the single-process
``codepost-mcp`` container (and a single uvicorn in dev), which is what makes
an in-memory dict — and the elicitation waiters in ``core/mcp/elicitation.py``
— correct. Scaling `/mcp` to multiple processes would silently break both;
don't, without moving this state to Redis first.
"""
from __future__ import annotations

import threading
import time
import uuid

SESSION_TTL_SECONDS = 12 * 3600
MAX_SESSIONS = 10_000

_lock = threading.Lock()
_sessions: dict[str, dict] = {}


def create(capabilities: dict) -> str:
    """Mint a session id for a client whose capabilities warrant one."""
    session_id = uuid.uuid4().hex
    with _lock:
        _prune_locked()
        if len(_sessions) >= MAX_SESSIONS:
            # Drop the oldest rather than refuse — a session is a convenience,
            # and the affected client simply falls back to stateless behaviour.
            oldest = min(_sessions, key=lambda k: _sessions[k]['created'])
            del _sessions[oldest]
        _sessions[session_id] = {
            'elicitation': 'elicitation' in (capabilities or {}),
            'created': time.monotonic(),
        }
    return session_id


def get(session_id: str | None) -> dict | None:
    if not session_id:
        return None
    with _lock:
        _prune_locked()
        return _sessions.get(session_id)


def _prune_locked() -> None:
    cutoff = time.monotonic() - SESSION_TTL_SECONDS
    stale = [k for k, v in _sessions.items() if v['created'] < cutoff]
    for k in stale:
        del _sessions[k]
