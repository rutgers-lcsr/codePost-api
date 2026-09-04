# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""OAuth Bearer tokens against the MCP endpoint: challenge, scopes, audience."""
import json
from datetime import timedelta

import factory
import pytest
from django.db.models.signals import post_save
from django.test import Client
from django.utils import timezone

API = "http://localhost:8000"
MCP_HOST = "localhost:8000"          # must match the bound resource for RFC 8707


@pytest.fixture
def course(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs-moauth", period="f2026",
                             organization__name="TestOrg")


@pytest.fixture
def instructor(course):
    return course.courseAdmins.first()


@pytest.fixture
def app(db):
    from oauth2_provider.models import Application
    return Application.objects.create(
        name="Claude (test)", client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        client_secret="",
        redirect_uris="https://claude.ai/api/mcp/auth_callback")


def bearer(instructor, app, *, scope, resource=None):
    """Mint an AccessToken directly — flow mechanics are covered elsewhere."""
    from oauth2_provider.models import AccessToken
    return AccessToken.objects.create(
        user=instructor, application=app, token=f"tok-{scope.replace(' ', '-')}",
        scope=scope, expires=timezone.now() + timedelta(hours=1),
        resource=[resource] if resource else [])


def mcp(token, method="tools/list", params=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        body["params"] = params
    return Client().post(
        "/mcp", data=json.dumps(body), content_type="application/json",
        HTTP_HOST=MCP_HOST,
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_MCP_PROTOCOL_VERSION="2025-06-18")


class TestChallenge:

    def test_401_advertises_resource_metadata(self, db):
        resp = Client().post(
            "/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
            content_type="application/json")
        assert resp.status_code == 401
        challenge = resp["WWW-Authenticate"]
        assert challenge.startswith("Bearer")
        assert 'resource_metadata="' in challenge
        assert "/.well-known/oauth-protected-resource/mcp" in challenge


class TestScopes:

    def test_read_scope_sees_only_read_tools(self, instructor, app, course):
        token = bearer(instructor, app, scope="read", resource=f"{API}/mcp")
        resp = mcp(token.token)
        assert resp.status_code == 200, resp.content
        tools = resp.json()["result"]["tools"]
        assert tools
        assert all(t["annotations"]["readOnlyHint"] for t in tools)

    def test_write_scope_hides_tier3(self, instructor, app, course):
        token = bearer(instructor, app, scope="read write",
                       resource=f"{API}/mcp")
        names = {t["name"] for t in mcp(token.token).json()["result"]["tools"]}
        assert "codepost_create_assignment" in names
        assert "codepost_delete_resource" not in names

    def test_admin_scope_sees_everything(self, instructor, app, course):
        token = bearer(instructor, app, scope="read write admin",
                       resource=f"{API}/mcp")
        names = {t["name"] for t in mcp(token.token).json()["result"]["tools"]}
        assert "codepost_delete_resource" in names

    def test_scopeless_token_behaves_as_read(self, instructor, app, course):
        token = bearer(instructor, app, scope="", resource=f"{API}/mcp")
        tools = mcp(token.token).json()["result"]["tools"]
        assert tools and all(t["annotations"]["readOnlyHint"] for t in tools)

    def test_oauth_connection_is_unpinned(self, instructor, app, course):
        token = bearer(instructor, app, scope="read", resource=f"{API}/mcp")
        resp = mcp(token.token, "tools/call",
                   {"name": "codepost_list_courses", "arguments": {}})
        result = resp.json()["result"]
        assert result["isError"] is False, result["content"][0]["text"]
        rows = result["structuredContent"]["data"]["courses"]
        assert any(c["id"] == course.id for c in rows)

    def test_dispatched_tools_work_under_oauth(self, instructor, app, course):
        """The dispatcher exchanges the opaque Bearer for an internal JWT —
        without that, every dispatched viewset call would 401."""
        token = bearer(instructor, app, scope="read", resource=f"{API}/mcp")
        resp = mcp(token.token, "tools/call",
                   {"name": "codepost_get_course_overview",
                    "arguments": {"courseId": course.id}})
        result = resp.json()["result"]
        assert result["isError"] is False, result["content"][0]["text"]
        assert result["structuredContent"]["data"]["course"]["id"] == course.id


class TestAudience:

    def test_unbound_token_is_refused(self, instructor, app, course):
        """DOT skips audience validation for unbound tokens; our check closes
        that hole per the MCP spec's issued-specifically-for-us MUST."""
        token = bearer(instructor, app, scope="read", resource=None)
        resp = mcp(token.token, "ping")
        assert resp.status_code == 403
        assert "not bound" in resp.json()["detail"]
