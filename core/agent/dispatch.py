# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""In-process dispatch into the real DRF viewsets.

Every agent tool goes through here; nothing touches the ORM directly.  The
synthetic request replays the caller's own ``Authorization`` header, so
``CourseAPIKeyAuthentication`` runs for real and the request is
indistinguishable from an external one by the time it reaches a permission
class.  That means ``CoursePermissions`` / ``AssignmentPermissions`` / the
archived-course guard in ``ModelSerializerWithPOSTCheck.validate`` all apply
unchanged, with no duplicated permission logic to drift.

Middleware (CORS, CSRF, session) does not run, which is correct for an
internal call — and CSRF specifically cannot bite, because DRF only enforces
it when ``SessionAuthentication`` succeeds, which it can't here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from django.http import HttpResponse
from django.test import RequestFactory  # django.test, NOT rest_framework.test:
                                        # no test-only imports in production code

from core.agent import errors

_factory = RequestFactory()

# Headers replayed onto the synthetic request. A strict allowlist on purpose:
# forwarding Cookie would enable SessionAuthentication and CSRF surprises, so
# this tuple is a security boundary and has a test pinning it.
_REPLAYED_META = ('HTTP_AUTHORIZATION',)


@dataclass(frozen=True)
class DispatchResult:
    status: int
    data: Any

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class Dispatcher:
    """Binds one principal's credentials; each tool makes N calls through it."""

    def __init__(self, meta: dict[str, str], *, course_id: int | None):
        self._creds = {k: v for k, v in meta.items() if k in _REPLAYED_META}
        # None only for the courseless context behind course_bound=False tools;
        # assert_in_scope refuses to run without a pinned course.
        self._course_id = int(course_id) if course_id is not None else None

    def call(self, view_cls, actions: dict[str, str], *, method: str, path: str,
             data: Any = None, query: str = '', **url_kwargs) -> DispatchResult:
        """Invoke ``view_cls`` as if it had been reached over HTTP.

        ``actions`` maps HTTP verb to viewset method, e.g. ``{'get': 'retrieve'}``
        or ``{'patch': 'addToRoster'}`` for an ``@action``.
        """
        verb = method.lower()
        full_path = f'{path}?{query}' if query else path

        if verb in ('get', 'delete'):
            request = getattr(_factory, verb)(full_path, **self._creds)
        else:
            request = getattr(_factory, verb)(
                full_path,
                data=json.dumps(data or {}, default=str),
                content_type='application/json',
                **self._creds,
            )

        response = view_cls.as_view(actions)(request, **url_kwargs)

        # DRF Response exposes .data without needing a renderer. A few actions
        # (auditLogExport, download) return a plain HttpResponse instead.
        if hasattr(response, 'data'):
            return DispatchResult(response.status_code, response.data)
        if isinstance(response, HttpResponse):
            body = response.content.decode('utf-8', 'replace')
            return DispatchResult(response.status_code, body)
        return DispatchResult(response.status_code, None)

    def require(self, view_cls, actions, *, what: str, **kwargs) -> Any:
        """``call`` that raises a ToolError on failure and returns ``.data``."""
        result = self.call(view_cls, actions, **kwargs)
        if not result.ok:
            raise errors.from_dispatch(result, what=what)
        return result.data

    # -- Defence in depth ----------------------------------------------------

    def assert_in_scope(self, course_id: Any, *, what: str) -> None:
        """Fail closed if a payload names a course other than the scoped one.

        Cross-course access is already impossible — the service account is a
        courseAdmin of exactly one course — but agent tools compose several
        calls and pass ids between them, so this catches a mis-wired tool
        before it can surface another course's data.
        """
        if self._course_id is None:
            raise errors.not_in_scope(f'{what} (dispatcher has no course bound)')
        if course_id is None:
            raise errors.not_in_scope(f'{what} (no resolvable course)')
        if int(course_id) != self._course_id:
            raise errors.not_in_scope(what)
