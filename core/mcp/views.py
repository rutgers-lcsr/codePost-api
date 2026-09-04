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
from core.mcp.oauth import MCPOAuth2Authentication
from core.mcp import elicitation, protocol, sessions
from core.throttles import AgentToolThrottle


class MCPEndpointView(APIView):
    """MCP Streamable HTTP endpoint.

    Stateless JSON mode by default. The one exception: a client whose
    ``initialize`` declares the ``elicitation`` capability gets a session-lite
    ``Mcp-Session-Id`` (in-process — see ``core/mcp/sessions.py``), and its
    Tier-3 tool calls answer as an SSE stream carrying an in-chat approval
    dialog. GET and DELETE still answer 405, which the spec allows for servers
    offering no server-initiated GET stream and no client-side session
    termination.
    """

    # Course keys pin the course; personal instructor tokens (the SDK
    # credential) and OAuth Bearer tokens (Claude Desktop / claude.ai native
    # connectors) connect unpinned and choose the course per tool call via
    # codepost_list_courses + a courseId argument.
    #
    # MCPOAuth2Authentication is FIRST on purpose: DRF takes the 401
    # WWW-Authenticate challenge from the first authenticator, and the MCP auth
    # spec requires it to be `Bearer ... resource_metadata="..."`. The class
    # returns None for non-Bearer credentials, so the others are unaffected.
    authentication_classes = [MCPOAuth2Authentication,
                              CourseAPIKeyAuthentication,
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

        # RFC 8707 audience strictness: django-oauth-toolkit only audience-
        # validates tokens that carry a resource binding (a foreign-resource
        # token is already 401'd upstream); a token with NO binding would skip
        # the check entirely, so refuse it here — the MCP spec requires tokens
        # issued specifically for this server.
        from oauth2_provider.models import AccessToken as OAuthAccessToken
        if isinstance(request.auth, OAuthAccessToken) and not request.auth.resource:
            return Response(
                {'detail': 'This token is not bound to the MCP resource. '
                           'Reconnect so your client requests it with '
                           'resource=' + f'{ _api_url() }/mcp.'},
                status=403)

        # All credential flavours are welcome. A course key arrives pinned to
        # its course; a personal token or OAuth Bearer arrives unpinned and
        # every course-bound tool call must name a course the caller staffs —
        # enforcement lives in Connection.context_for, per call.
        conn = Connection(request)

        # A Tier-3 tool call from an elicitation-capable session answers as an
        # SSE stream so the approval dialog can be asked mid-call.
        if _wants_elicitation_stream(request):
            return _stream_tools_call(request.data, conn)

        try:
            result = protocol.handle(request.data, conn)
        except protocol.JSONRPCError as exc:
            return Response({'jsonrpc': '2.0', 'id': None,
                             'error': {'code': exc.code, 'message': exc.message}},
                            status=400)

        # A notification carries no id and gets 202 with an empty body, per spec.
        if result is None:
            return Response(status=202)

        response = Response(result)
        # Session-lite id minted by initialize (spec: delivered as a header on
        # the initialize response).
        new_session = getattr(conn, 'new_session_id', None)
        if new_session:
            response['Mcp-Session-Id'] = new_session
        return response


def _api_url() -> str:
    return getattr(settings, 'API_URL', '')


def _wants_elicitation_stream(request) -> bool:
    """True for a tools/call on a Tier-3 tool from an elicitation session.

    Everything else — every stateless client, every non-destructive tool —
    keeps the plain JSON response path untouched.
    """
    body = request.data
    if not isinstance(body, dict) or body.get('method') != 'tools/call':
        return False
    session = sessions.get(request.META.get('HTTP_MCP_SESSION_ID'))
    if not session or not session.get('elicitation'):
        return False

    from core.agent import registry
    registry.load_tools()
    name = (body.get('params') or {}).get('name')
    spec = registry.get(name) if isinstance(name, str) else None
    return spec is not None and getattr(spec, 'tier', 0) == 3


def _stream_tools_call(body, conn):
    """Answer one tools/call as an SSE stream that can carry an elicitation.

    The handler runs in a worker thread with a Channel attached to the
    connection; the generator forwards the channel's outbound frames (the
    ``elicitation/create`` request) as SSE events, then emits the final
    JSON-RPC response and closes. Per spec, a server MAY answer any POST with
    an SSE stream, and clients MUST accept both forms.
    """
    import json
    import threading

    from django.http import StreamingHttpResponse

    channel = elicitation.Channel()
    conn.elicit_channel = channel
    holder = {}

    def worker():
        try:
            holder['response'] = protocol.handle(body, conn)
        except protocol.JSONRPCError as exc:
            holder['response'] = {
                'jsonrpc': '2.0', 'id': body.get('id'),
                'error': {'code': exc.code, 'message': exc.message}}
        finally:
            channel.close()

    def stream():
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        for frame in channel.drain():
            yield f'data: {json.dumps(frame, default=str)}\n\n'
        thread.join()
        yield f'data: {json.dumps(holder.get("response"), default=str)}\n\n'

    response = StreamingHttpResponse(stream(),
                                     content_type='text/event-stream')
    response['Cache-Control'] = 'no-store'
    response['X-Accel-Buffering'] = 'no'
    return response


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
