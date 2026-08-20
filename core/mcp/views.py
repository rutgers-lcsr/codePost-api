# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The MCP endpoint.

Sync on purpose: Django's ASGIHandler runs sync views in a threadpool, so the
ORM works without ``sync_to_async`` and the four uvicorn event loops are never
blocked.  Long-running work (autograder runs, imports) must never be done
inline — those tools return a job id and pair with a polling tool.
"""
from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.authentication import TokenAuthentication

from core.agent.context import Connection
from core.authentication import (CourseAPIKeyAuthentication,
                                 CourseScopedJWTAuthentication)
from core.mcp import protocol
from core.throttles import AgentToolThrottle


class MCPEndpointView(APIView):
    """MCP Streamable HTTP endpoint, stateless JSON mode.

    Stateless means we never issue ``Mcp-Session-Id``, so any worker can serve
    any request. GET and DELETE answer 405, which the spec explicitly allows
    for servers offering no server-initiated SSE stream and no client-side
    session termination.
    """

    # Course keys pin the course; personal instructor tokens (the SDK
    # credential) connect unpinned and choose the course per tool call via
    # codepost_list_courses + a courseId argument.
    authentication_classes = [CourseAPIKeyAuthentication,
                              CourseScopedJWTAuthentication,
                              TokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AgentToolThrottle]
    schema = None                       # keep out of schema.yaml and the TS client

    def get(self, request, *args, **kwargs):
        return Response(status=405, headers={'Allow': 'POST'})

    def delete(self, request, *args, **kwargs):
        return Response(status=405, headers={'Allow': 'POST'})

    def post(self, request, *args, **kwargs):
        origin_error = _validate_origin(request)
        if origin_error:
            return origin_error

        version_error = _validate_protocol_version(request)
        if version_error:
            return version_error

        # Both credential flavours are welcome. A course key arrives pinned to
        # its course; a personal token arrives unpinned and every course-bound
        # tool call must name a course the caller staffs — enforcement lives in
        # Connection.context_for, per call.
        conn = Connection(request)

        try:
            result = protocol.handle(request.data, conn)
        except protocol.JSONRPCError as exc:
            return Response({'jsonrpc': '2.0', 'id': None,
                             'error': {'code': exc.code, 'message': exc.message}},
                            status=400)

        # A notification carries no id and gets 202 with an empty body, per spec.
        if result is None:
            return Response(status=202)
        return Response(result)


def _validate_origin(request):
    """Reject cross-origin browser requests (DNS rebinding).

    The spec makes Origin validation a MUST. Non-browser clients send no
    Origin at all, which is the normal case here.
    """
    origin = request.META.get('HTTP_ORIGIN')
    if not origin:
        return None

    host = urlparse(origin).hostname
    if not host:
        return Response({'detail': 'Invalid Origin header.'}, status=403)

    allowed = {urlparse(url).hostname
               for url in getattr(settings, 'CORS_ALLOWED_ORIGINS', [])}
    allowed.discard(None)
    if settings.DEBUG:
        allowed.update({'localhost', '127.0.0.1'})

    if host in allowed:
        return None
    return Response({'detail': f'Origin {origin} is not allowed.'}, status=403)


def _validate_protocol_version(request):
    """A bad MCP-Protocol-Version is an HTTP 400, not a JSON-RPC error.

    Absent means the client predates the header, so assume the revision that
    introduced it rather than failing.
    """
    version = request.META.get('HTTP_MCP_PROTOCOL_VERSION')
    if version is None:
        return None
    if version in protocol.SUPPORTED_PROTOCOL_VERSIONS:
        return None
    return Response(
        {'detail': f'Unsupported MCP-Protocol-Version: {version}.',
         'supported': list(protocol.SUPPORTED_PROTOCOL_VERSIONS)},
        status=400)
