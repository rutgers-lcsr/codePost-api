# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The OAuth 2.1 authorization server: metadata, PKCE flow, DCR, redirects.

These pin the MCP auth spec's MUSTs (RFC 8414/9728 discovery, PKCE-S256,
resource indicators) against our django-oauth-toolkit mount.
"""
import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlparse

import factory
import pytest
from django.db.models.signals import post_save
from django.test import Client

API = "http://localhost:8000"      # settings API_URL default in tests


@pytest.fixture
def course(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs-oauth", period="f2026",
                             organization__name="TestOrg")


@pytest.fixture
def instructor(course):
    admin = course.courseAdmins.first()
    admin.set_password("hunter2hunter2")
    admin.save()
    return admin


@pytest.fixture
def claude_app(db):
    from oauth2_provider.models import Application
    return Application.objects.create(
        name="Claude (test)",
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        client_secret="",
        redirect_uris="https://claude.ai/api/mcp/auth_callback "
                      "http://localhost/callback",
    )


def pkce_pair():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def run_authorize(client, app, *, challenge, resource=None,
                  redirect_uri="https://claude.ai/api/mcp/auth_callback",
                  scope="read write admin"):
    params = {
        "client_id": app.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": "xyz",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if resource:
        params["resource"] = resource
    resp = client.get("/o/authorize/", params)
    assert resp.status_code == 200, getattr(resp, "url", resp.status_code)
    form = {"client_id": app.client_id, "redirect_uri": redirect_uri,
            "response_type": "code", "scope": scope, "state": "xyz",
            "code_challenge": challenge, "code_challenge_method": "S256",
            "allow": "Authorize"}
    if resource:
        form["resource"] = resource
    resp = client.post("/o/authorize/", form)
    assert resp.status_code == 302, resp.content
    query = parse_qs(urlparse(resp["Location"]).query)
    return query


class TestMetadata:

    def test_authorization_server_metadata(self, db):
        d = Client().get("/.well-known/oauth-authorization-server").json()
        assert d["issuer"] == API
        assert d["authorization_endpoint"].endswith("/o/authorize/")
        assert d["token_endpoint"].endswith("/o/token/")
        assert d["registration_endpoint"].endswith("/o/register/")
        assert d["code_challenge_methods_supported"] == ["S256"]
        assert set(d["scopes_supported"]) == {"read", "write", "admin"}
        assert set(d["grant_types_supported"]) == {"authorization_code",
                                                  "refresh_token"}

    def test_protected_resource_metadata_both_forms(self, db):
        for path in ("/.well-known/oauth-protected-resource",
                     "/.well-known/oauth-protected-resource/mcp"):
            d = Client().get(path).json()
            assert d["resource"] == f"{API}/mcp", path
            assert d["authorization_servers"] == [API]


class TestAuthorizationCodeFlow:

    def test_anonymous_authorize_redirects_to_agent_login(self, claude_app):
        _, challenge = pkce_pair()
        resp = Client().get("/o/authorize/", {
            "client_id": claude_app.client_id, "response_type": "code",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "code_challenge": challenge, "code_challenge_method": "S256"})
        assert resp.status_code == 302
        assert resp["Location"].startswith("/auth/agent-login/?next=")

    def test_full_pkce_flow_yields_working_bearer(self, claude_app, instructor,
                                                  course):
        client = Client()
        client.force_login(instructor)
        verifier, challenge = pkce_pair()

        query = run_authorize(client, claude_app, challenge=challenge,
                              resource=f"{API}/mcp")
        assert "code" in query
        assert query.get("iss") == [API]          # RFC 9207

        resp = client.post("/o/token/", {
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": claude_app.client_id,
            "code_verifier": verifier,
            "resource": f"{API}/mcp",
        })
        assert resp.status_code == 200, resp.content
        tokens = resp.json()
        assert tokens["token_type"].lower() == "bearer"
        assert "refresh_token" in tokens
        assert set(tokens["scope"].split()) == {"read", "write", "admin"}

        # The Bearer token drives the MCP endpoint as an unpinned connection.
        # HTTP_HOST must match the bound resource (API_URL): the RFC 8707
        # prefix validator rejects any other request URI — which is also what
        # test_foreign_host_is_rejected pins below.
        mcp = Client().post(
            "/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 1,
                                     "method": "tools/list"}),
            content_type="application/json",
            HTTP_HOST="localhost:8000",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
            HTTP_MCP_PROTOCOL_VERSION="2025-06-18")
        assert mcp.status_code == 200, mcp.content
        names = {t["name"] for t in mcp.json()["result"]["tools"]}
        assert "codepost_list_courses" in names          # unpinned surface

        # Refresh rotation
        refreshed = client.post("/o/token/", {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": claude_app.client_id,
        })
        assert refreshed.status_code == 200, refreshed.content
        assert refreshed.json()["access_token"] != tokens["access_token"]

    def test_resource_bound_token_rejected_on_foreign_host(
            self, claude_app, instructor, course):
        """RFC 8707 audience validation: a token bound to API_URL/mcp must not
        authenticate a request presented under any other host."""
        client = Client()
        client.force_login(instructor)
        verifier, challenge = pkce_pair()
        query = run_authorize(client, claude_app, challenge=challenge,
                              resource=f"{API}/mcp")
        tokens = client.post("/o/token/", {
            "grant_type": "authorization_code", "code": query["code"][0],
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": claude_app.client_id, "code_verifier": verifier,
            "resource": f"{API}/mcp"}).json()

        mcp = Client().post(
            "/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
            HTTP_MCP_PROTOCOL_VERSION="2025-06-18")   # host: testserver
        assert mcp.status_code == 401

    def test_missing_pkce_is_rejected(self, claude_app, instructor):
        client = Client()
        client.force_login(instructor)
        resp = client.get("/o/authorize/", {
            "client_id": claude_app.client_id, "response_type": "code",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback"})
        # PKCE_REQUIRED: no challenge -> error response, never a consent page
        assert (resp.status_code != 200 or b"error" in resp.content)

    def test_loopback_redirect_matches_any_port(self, claude_app, instructor):
        client = Client()
        client.force_login(instructor)
        verifier, challenge = pkce_pair()
        query = run_authorize(client, claude_app, challenge=challenge,
                              redirect_uri="http://localhost:53211/callback")
        assert "code" in query

    def test_unregistered_redirect_uri_rejected(self, claude_app, instructor):
        client = Client()
        client.force_login(instructor)
        _, challenge = pkce_pair()
        resp = client.get("/o/authorize/", {
            "client_id": claude_app.client_id, "response_type": "code",
            "redirect_uri": "https://evil.example.com/callback",
            "code_challenge": challenge, "code_challenge_method": "S256"})
        assert resp.status_code == 400


class TestDCR:

    CLAUDE_BODY = {
        "client_name": "Claude",
        "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }

    def test_claude_shaped_registration_succeeds(self, db):
        resp = Client().post("/o/register/", data=json.dumps(self.CLAUDE_BODY),
                             content_type="application/json")
        assert resp.status_code == 201, resp.content
        data = resp.json()
        assert data["client_id"]
        assert data["token_endpoint_auth_method"] == "none"

        from oauth2_provider.models import Application
        app = Application.objects.get(client_id=data["client_id"])
        assert app.client_type == Application.CLIENT_PUBLIC

    def test_dcr_registration_is_audited(self, db):
        from log.models import Event
        Client().post("/o/register/", data=json.dumps(self.CLAUDE_BODY),
                      content_type="application/json")
        event = Event.objects.filter(category="oauth",
                                     description="oauth_dcr_registered").latest("created")
        assert "Claude" in event.meta

    def test_dcr_disabled_hides_endpoint(self, db, settings):
        settings.OAUTH2_PROVIDER = {**settings.OAUTH2_PROVIDER,
                                    "DCR_ENABLED": False}
        # oauth2_settings caches; re-read via a fresh attribute access
        from oauth2_provider.settings import oauth2_settings
        oauth2_settings.reload()
        try:
            resp = Client().post("/o/register/",
                                 data=json.dumps(self.CLAUDE_BODY),
                                 content_type="application/json")
            assert resp.status_code == 404
        finally:
            oauth2_settings.reload()
