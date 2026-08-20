# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""MCP endpoint conformance.

Since we implement the protocol ourselves rather than pulling in an SDK, these
are the regression net for the wire format. Each one pins a MUST from the
2025-06-18 Streamable HTTP spec.
"""
import factory
import pytest
from django.db.models.signals import post_save
from rest_framework import status
from rest_framework.test import APIClient

MCP_URL = "/mcp"
PROTOCOL_VERSION = "2025-06-18"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def course_a(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs101", period="f2026", organization__name="TestOrg")


@pytest.fixture
def course_b(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs202", period="f2026", organization__name="TestOrg")


@pytest.fixture
def admin_of_a(course_a):
    return course_a.courseAdmins.first()


@pytest.fixture
def api_client():
    return APIClient()


def _mint_key(api_client, course, admin, *, scope="admin", name="mcp-key"):
    api_client.force_authenticate(user=admin)
    resp = api_client.post(f"/courses/{course.id}/apiKeys/",
                           {"name": name, "scope": scope}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    api_client.force_authenticate(user=None)
    return resp.data["key"]


@pytest.fixture
def admin_key(api_client, course_a, admin_of_a):
    return _mint_key(api_client, course_a, admin_of_a, scope="admin")


@pytest.fixture
def read_key(api_client, course_a, admin_of_a):
    return _mint_key(api_client, course_a, admin_of_a, scope="read", name="read-key")


def _rpc(api_client, key, method, params=None, request_id=1, **extra):
    body = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        body["id"] = request_id
    if params is not None:
        body["params"] = params
    api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {key}",
                           HTTP_MCP_PROTOCOL_VERSION=PROTOCOL_VERSION, **extra)
    return api_client.post(MCP_URL, body, format="json")


# ---------------------------------------------------------------------------
# Handshake and transport
# ---------------------------------------------------------------------------

class TestHandshake:

    def test_initialize_declares_tools_capability(self, api_client, admin_key):
        resp = _rpc(api_client, admin_key, "initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        })
        assert resp.status_code == status.HTTP_200_OK
        result = resp.data["result"]
        assert result["protocolVersion"] == PROTOCOL_VERSION
        assert result["capabilities"]["tools"] == {"listChanged": False}
        assert result["serverInfo"]["name"] == "codepost"

    def test_initialize_negotiates_down_unknown_version(self, api_client, admin_key):
        """An unknown version in the body is answered with ours, not an error."""
        resp = _rpc(api_client, admin_key, "initialize",
                    {"protocolVersion": "1999-01-01", "capabilities": {}})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["result"]["protocolVersion"] == PROTOCOL_VERSION

    def test_notification_returns_202_with_empty_body(self, api_client, admin_key):
        """Spec: notifications get 202 Accepted and no body — not a JSON-RPC reply."""
        resp = _rpc(api_client, admin_key, "notifications/initialized",
                    request_id=None)
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert not resp.data

    def test_ping(self, api_client, admin_key):
        resp = _rpc(api_client, admin_key, "ping")
        assert resp.data["result"] == {}

    def test_get_returns_405(self, api_client, admin_key):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {admin_key}")
        resp = api_client.get(MCP_URL)
        assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_delete_returns_405(self, api_client, admin_key):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {admin_key}")
        resp = api_client.delete(MCP_URL)
        assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_unsupported_protocol_version_header_is_400(self, api_client, admin_key):
        """Spec: an invalid MCP-Protocol-Version MUST be an HTTP 400."""
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {admin_key}",
                               HTTP_MCP_PROTOCOL_VERSION="1999-01-01")
        resp = api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                               format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_protocol_version_header_is_accepted(self, api_client, admin_key):
        """Absent header means a pre-header client; assume, don't fail."""
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {admin_key}")
        resp = api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                               format="json")
        assert resp.status_code == status.HTTP_200_OK

    def test_batching_is_rejected(self, api_client, admin_key):
        """JSON-RPC batching was removed in the 2025-06-18 revision."""
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {admin_key}")
        resp = api_client.post(
            MCP_URL, [{"jsonrpc": "2.0", "id": 1, "method": "ping"}], format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_stateless_never_issues_session_id(self, api_client, admin_key):
        """Four round-robined workers only work if there is no session to strand."""
        resp = _rpc(api_client, admin_key, "initialize",
                    {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}})
        assert "Mcp-Session-Id" not in resp

    def test_disallowed_origin_rejected(self, api_client, admin_key):
        """Origin validation is a spec MUST (DNS rebinding)."""
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {admin_key}",
                               HTTP_ORIGIN="https://evil.example.com")
        resp = api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                               format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Authentication and scoping
# ---------------------------------------------------------------------------

class TestMCPAuth:

    def test_unauthenticated_rejected(self, api_client, db):
        resp = api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                               format="json")
        assert resp.status_code in (status.HTTP_401_UNAUTHORIZED,
                                    status.HTTP_403_FORBIDDEN)

    def test_unscoped_credential_connects_unpinned(self, api_client, admin_of_a):
        """Personal (unscoped) credentials connect fine — they just choose the
        course per call. tools/list shows codepost_list_courses and injects a
        required courseId into every course-bound schema."""
        api_client.force_authenticate(user=admin_of_a)
        resp = api_client.post(
            MCP_URL, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            format="json")
        assert resp.status_code == status.HTTP_200_OK
        tools = {t["name"]: t for t in resp.data["result"]["tools"]}
        assert "codepost_list_courses" in tools
        overview = tools["codepost_get_course_overview"]
        assert "courseId" in overview["inputSchema"]["properties"]
        assert "courseId" in overview["inputSchema"]["required"]
        # list_courses itself is course-free
        assert "courseId" not in tools["codepost_list_courses"]["inputSchema"]["properties"]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class TestToolsList:

    def test_lists_read_tools(self, api_client, admin_key):
        resp = _rpc(api_client, admin_key, "tools/list")
        names = {t["name"] for t in resp.data["result"]["tools"]}
        assert "codepost_get_course_overview" in names
        # Every tool is namespaced; MCP tool names are global across servers.
        assert all(n.startswith("codepost_") for n in names)

    def test_descriptors_carry_annotations(self, api_client, admin_key):
        resp = _rpc(api_client, admin_key, "tools/list")
        tool = next(t for t in resp.data["result"]["tools"]
                    if t["name"] == "codepost_get_course_overview")
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["openWorldHint"] is False
        assert tool["inputSchema"]["type"] == "object"

    def test_read_key_sees_only_read_tools(self, api_client, read_key):
        resp = _rpc(api_client, read_key, "tools/list")
        tools = resp.data["result"]["tools"]
        assert tools, "a read key should still see the read tools"
        assert all(t["annotations"]["readOnlyHint"] for t in tools)


class TestToolsCall:

    def test_course_overview_returns_this_course(self, api_client, admin_key, course_a):
        resp = _rpc(api_client, admin_key, "tools/call",
                    {"name": "codepost_get_course_overview", "arguments": {}})
        result = resp.data["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["data"]["course"]["id"] == course_a.id
        # Spec: structured content SHOULD also be serialised into a text block.
        assert result["content"][0]["type"] == "text"

    def test_unknown_tool_is_a_protocol_error(self, api_client, admin_key):
        """Unknown tool => JSON-RPC error, not an isError result."""
        resp = _rpc(api_client, admin_key, "tools/call",
                    {"name": "codepost_not_a_tool", "arguments": {}})
        assert resp.data["error"]["code"] == -32601

    def test_missing_required_argument_is_a_protocol_error(self, api_client, admin_key):
        resp = _rpc(api_client, admin_key, "tools/call",
                    {"name": "codepost_get_assignment", "arguments": {}})
        assert resp.data["error"]["code"] == -32602
        assert "assignmentId" in resp.data["error"]["message"]

    def test_unknown_argument_is_rejected_with_valid_names(self, api_client, admin_key):
        resp = _rpc(api_client, admin_key, "tools/call",
                    {"name": "codepost_get_course_overview",
                     "arguments": {"assignmentIds": [1]}})
        assert resp.data["error"]["code"] == -32602
        assert "assignmentIds" in resp.data["error"]["message"]

    def test_mismatched_course_id_on_pinned_key_is_refused(
            self, api_client, admin_key, course_a, course_b):
        """courseId is adapter-level: a course key tolerates its own course's id
        but refuses any other, with a remedy saying the key implies the course."""
        import json

        resp = _rpc(api_client, admin_key, "tools/call",
                    {"name": "codepost_get_course_overview",
                     "arguments": {"courseId": course_b.id}})
        result = resp.data["result"]
        assert result["isError"] is True
        payload = json.loads(result["content"][0]["text"])
        assert payload["error"]["code"] == "NOT_IN_SCOPE"

        # The key's own course id is harmless.
        resp = _rpc(api_client, admin_key, "tools/call",
                    {"name": "codepost_get_course_overview",
                     "arguments": {"courseId": course_a.id}})
        assert resp.data["result"]["isError"] is False

    def test_bad_enum_value_is_rejected(self, api_client, admin_key):
        resp = _rpc(api_client, admin_key, "tools/call",
                    {"name": "codepost_get_roster", "arguments": {"view": "nonsense"}})
        assert resp.data["error"]["code"] == -32602

    def test_cross_course_assignment_is_an_iserror_result(
            self, api_client, admin_key, course_b):
        """Business-logic failures are results with isError, never protocol errors.

        Also the cross-course check: a course_a key must not read course_b's
        assignment. Error results carry no structuredContent — it would have to
        conform to the tool's outputSchema, and an error does not.
        """
        import json

        with factory.django.mute_signals(post_save):
            from core.tests.factories import AssignmentFactory
            other = AssignmentFactory(course=course_b)

        resp = _rpc(api_client, admin_key, "tools/call",
                    {"name": "codepost_get_assignment",
                     "arguments": {"assignmentId": other.id}})
        result = resp.data["result"]
        assert result["isError"] is True
        assert "structuredContent" not in result

        payload = json.loads(result["content"][0]["text"])
        assert payload["error"]["code"] in ("NOT_IN_SCOPE", "MISSING_CAPABILITY",
                                            "NOT_FOUND")
        assert payload["error"]["retryable"] is False

# ---------------------------------------------------------------------------
# Personal instructor tokens (unpinned connections)
# ---------------------------------------------------------------------------

@pytest.fixture
def personal_token(admin_of_a):
    """A DRF Token for the instructor — the credential the Python SDK uses."""
    from rest_framework.authtoken.models import Token
    token, _ = Token.objects.get_or_create(user=admin_of_a)
    return token.key


def _token_rpc(api_client, token, method, params=None, request_id=1, url=MCP_URL):
    body = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        body["id"] = request_id
    if params is not None:
        body["params"] = params
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token}",
                           HTTP_MCP_PROTOCOL_VERSION=PROTOCOL_VERSION)
    return api_client.post(url, body, format="json")


class TestPersonalTokens:

    def test_instructions_tell_token_users_to_list_courses(
            self, api_client, personal_token):
        resp = _token_rpc(api_client, personal_token, "initialize",
                          {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}})
        assert "codepost_list_courses" in resp.data["result"]["instructions"]

    def test_list_courses_returns_staffed_courses_with_roles(
            self, api_client, personal_token, course_a, admin_of_a):
        resp = _token_rpc(api_client, personal_token, "tools/call",
                          {"name": "codepost_list_courses", "arguments": {}})
        result = resp.data["result"]
        assert result["isError"] is False
        rows = result["structuredContent"]["data"]["courses"]
        mine = next(c for c in rows if c["id"] == course_a.id)
        assert "courseAdmin" in mine["roles"]

    def test_course_bound_tool_without_course_id_says_how_to_get_one(
            self, api_client, personal_token):
        import json
        resp = _token_rpc(api_client, personal_token, "tools/call",
                          {"name": "codepost_get_course_overview", "arguments": {}})
        result = resp.data["result"]
        assert result["isError"] is True
        payload = json.loads(result["content"][0]["text"])
        assert payload["error"]["code"] == "COURSE_REQUIRED"
        assert "codepost_list_courses" in payload["error"]["remedy"]
        assert payload["error"]["retryable"] is True

    def test_course_id_resolves_and_tools_work(
            self, api_client, personal_token, course_a):
        resp = _token_rpc(api_client, personal_token, "tools/call",
                          {"name": "codepost_get_course_overview",
                           "arguments": {"courseId": course_a.id}})
        result = resp.data["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["data"]["course"]["id"] == course_a.id

    def test_unstaffed_course_is_refused(
            self, api_client, personal_token, course_b):
        """admin_of_a staffs course_a only; course_b must be out of reach."""
        import json
        resp = _token_rpc(api_client, personal_token, "tools/call",
                          {"name": "codepost_get_course_overview",
                           "arguments": {"courseId": course_b.id}})
        result = resp.data["result"]
        assert result["isError"] is True
        payload = json.loads(result["content"][0]["text"])
        assert payload["error"]["code"] == "NOT_IN_SCOPE"

    def test_pinned_connection_never_sees_list_courses(self, api_client, admin_key):
        resp = _rpc(api_client, admin_key, "tools/list")
        names = {t["name"] for t in resp.data["result"]["tools"]}
        assert "codepost_list_courses" not in names
        # ...and its schemas carry no courseId either.
        resp2 = _rpc(api_client, admin_key, "tools/list")
        overview = next(t for t in resp2.data["result"]["tools"]
                        if t["name"] == "codepost_get_course_overview")
        assert "courseId" not in overview["inputSchema"]["properties"]

    def test_scope_query_param_narrows_a_token_connection(
            self, api_client, personal_token):
        """?scope=read self-limits a personal credential to the read tools."""
        resp = _token_rpc(api_client, personal_token, "tools/list",
                          url=MCP_URL + "?scope=read")
        tools = resp.data["result"]["tools"]
        assert tools
        assert all(t["annotations"]["readOnlyHint"] for t in tools)
