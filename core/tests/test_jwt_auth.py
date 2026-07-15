# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests for the access + refresh JWT auth model.

Covers:
- Password login returns an access + refresh pair (plus the ``token`` alias).
- The access token authenticates requests; an expired access token is rejected.
- Refreshing with the refresh token issues a new access token (rotation).
- The core fix: an *expired access token* + valid refresh token still refreshes.
- Refresh-token rotation blacklists the old token (reuse detection).
- /logout/ revokes a single session; /logout-all/ revokes every session.
"""
from datetime import timedelta

import factory
import pytest
from django.db.models.signals import post_save
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from core.models import User

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def user(db):
    """A user with a usable (hashed) password so the login endpoint works."""
    with factory.django.mute_signals(post_save):
        u = User.objects.create_user(
            username="jwtuser@test.edu", email="jwtuser@test.edu", password=PASSWORD,
        )
    return u


@pytest.fixture
def api_client():
    return APIClient()


def _login(api_client, user):
    resp = api_client.post(
        "/token-auth/", {"username": user.username, "password": PASSWORD}, format="json",
    )
    assert resp.status_code == status.HTTP_200_OK, resp.content
    return resp.data


def _bearer(api_client, token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_returns_access_and_refresh(api_client, user):
    data = _login(api_client, user)
    assert "access" in data and "refresh" in data
    # Backward-compatible alias used by existing clients.
    assert data["token"] == data["access"]
    # Access token carries the custom claims.
    access = AccessToken(data["access"])
    assert access["user_id"] == user.id
    assert access["email"] == user.email


def test_access_token_authenticates_request(api_client, user):
    data = _login(api_client, user)
    _bearer(api_client, data["access"])
    resp = api_client.get("/registration/current_user/")
    assert resp.status_code == status.HTTP_200_OK
    # current_user hands back a refresh token (this is how SSO bootstraps one).
    assert "refresh" in resp.data


# ---------------------------------------------------------------------------
# Refresh + rotation
# ---------------------------------------------------------------------------

def test_refresh_issues_new_access(api_client, user):
    data = _login(api_client, user)
    resp = api_client.post("/token-refresh/", {"refresh": data["refresh"]}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert "access" in resp.data
    # Rotation is enabled, so a new refresh token comes back too.
    assert "refresh" in resp.data
    assert resp.data["refresh"] != data["refresh"]


def test_refresh_rotation_blacklists_old_token(api_client, user):
    data = _login(api_client, user)
    first = api_client.post("/token-refresh/", {"refresh": data["refresh"]}, format="json")
    assert first.status_code == status.HTTP_200_OK
    # Reusing the now-rotated refresh token must be rejected (reuse detection).
    reuse = api_client.post("/token-refresh/", {"refresh": data["refresh"]}, format="json")
    assert reuse.status_code == status.HTTP_401_UNAUTHORIZED


def test_expired_access_rejected_but_refresh_still_works(api_client, user):
    """The reported bug: idling past the access lifetime must NOT log you out —
    the refresh token still refreshes even though the access token has expired."""
    data = _login(api_client, user)

    # Forge an already-expired access token for this user.
    expired = AccessToken()
    expired["user_id"] = user.id
    expired.set_exp(from_time=expired.current_time - timedelta(hours=1))
    _bearer(api_client, str(expired))
    resp = api_client.get("/registration/current_user/")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    # ...but the refresh token (still valid) mints a fresh access token.
    api_client.credentials()  # clear the expired bearer
    refreshed = api_client.post("/token-refresh/", {"refresh": data["refresh"]}, format="json")
    assert refreshed.status_code == status.HTTP_200_OK
    _bearer(api_client, refreshed.data["access"])
    ok = api_client.get("/registration/current_user/")
    assert ok.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Logout / revocation
# ---------------------------------------------------------------------------

def test_logout_blacklists_refresh_token(api_client, user):
    data = _login(api_client, user)
    _bearer(api_client, data["access"])
    out = api_client.post("/logout/", {"refresh": data["refresh"]}, format="json")
    assert out.status_code == status.HTTP_200_OK

    # The revoked refresh token can no longer be used.
    api_client.credentials()
    resp = api_client.post("/token-refresh/", {"refresh": data["refresh"]}, format="json")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_logout_all_revokes_every_session(api_client, user):
    # Two independent sessions.
    session_a = _login(api_client, user)
    session_b = _login(APIClient(), user)

    _bearer(api_client, session_a["access"])
    out = api_client.post("/logout-all/")
    assert out.status_code == status.HTTP_200_OK

    api_client.credentials()
    for session in (session_a, session_b):
        resp = api_client.post("/token-refresh/", {"refresh": session["refresh"]}, format="json")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
