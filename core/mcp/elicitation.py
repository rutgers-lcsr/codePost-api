# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Cross-request elicitation plumbing.

An elicitation is a server→client JSON-RPC request ("ask the human to approve
this") sent on the SSE stream of an in-flight ``tools/call`` POST. The client
shows its native dialog and sends the human's answer back as a JSON-RPC
*response* in a separate HTTP POST — a different request, same process (see
``core/mcp/sessions.py`` for why single-process is load-bearing). This module
is the rendezvous between the two.

The model never sees the dialog: the client renders it and answers on the
human's behalf, which is what lets Tier-3 confirmations keep their
prompt-injection resistance without the dashboard round-trip.
"""
from __future__ import annotations

import queue
import threading
import uuid
from typing import Any

from django.conf import settings

from core.agent.errors import ToolError

DEFAULT_TIMEOUT_SECONDS = 240

# Sentinel closing a channel's outbox.
_CLOSE = object()

_lock = threading.Lock()
_waiters: dict[str, dict] = {}


class Channel:
    """One streaming ``tools/call``'s pipe to its SSE generator.

    The tool handler runs in a worker thread; ``elicit`` pushes the outbound
    request onto ``outbox`` (drained by the generator into the SSE stream) and
    blocks until ``deliver`` hands over the client's response.
    """

    def __init__(self):
        self.outbox: queue.Queue = queue.Queue()

    def elicit(self, message: str, requested_schema: dict,
               timeout: float | None = None) -> dict:
        """Ask the human; return the client's ``{'action': …, 'content': …}``.

        A response carrying a JSON-RPC error (client refused or cannot render
        the dialog) is reported as ``{'action': 'cancel'}`` — never as
        approval.
        """
        if timeout is None:
            timeout = getattr(settings, 'MCP_ELICIT_TIMEOUT_SECONDS',
                              DEFAULT_TIMEOUT_SECONDS)
        request_id = f'elicit-{uuid.uuid4().hex}'
        waiter = {'event': threading.Event(), 'response': None}
        with _lock:
            _waiters[request_id] = waiter

        try:
            self.outbox.put({
                'jsonrpc': '2.0',
                'id': request_id,
                'method': 'elicitation/create',
                'params': {'message': message,
                           'requestedSchema': requested_schema},
            })
            if not waiter['event'].wait(timeout):
                raise ToolError(
                    'CONFIRMATION_REQUIRED',
                    'The approval dialog timed out before the user answered.',
                    remedy='Ask the user whether to proceed, then call the '
                           'tool again to show the dialog once more.',
                    retryable=True)
        finally:
            with _lock:
                _waiters.pop(request_id, None)

        body = waiter['response'] or {}
        if 'error' in body:
            return {'action': 'cancel'}
        result = body.get('result')
        return result if isinstance(result, dict) else {'action': 'cancel'}

    def close(self) -> None:
        self.outbox.put(_CLOSE)

    def drain(self):
        """Yield outbound frames until the channel closes."""
        while True:
            frame = self.outbox.get()
            if frame is _CLOSE:
                return
            yield frame


def deliver(request_id: Any, body: dict) -> bool:
    """Route a client's JSON-RPC response to the waiting elicitation, if any.

    Request ids are 128-bit random, so a response can only realistically come
    from the client that received the request.
    """
    with _lock:
        waiter = _waiters.get(request_id)
        if waiter is None:
            return False
        waiter['response'] = body
    waiter['event'].set()
    return True
