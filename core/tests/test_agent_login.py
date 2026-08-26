# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The OAuth login bridge: /auth/agent-login/ and the SSO `next` threading.

The load-bearing property: a Django session is created ONLY when the OAuth
flow's validated `next` parameter rides along — every normal SSO login keeps
today's JWT-redirect behaviour byte-for-byte.
"""
from unittest import mock
from urllib.parse import quote

import factory
import pytest
from django.db.models.signals import post_save
from django.test import Client

NEXT = "/o/authorize?client_id=abc&response_type=code"

CAS_SUCCESS_XML = b"""<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess><cas:user>jdoe</cas:user></cas:authenticationSuccess>
</cas:serviceResponse>"""


@pytest.fixture
def sso_org(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        course = CourseFactory(name="cs-sso", period="f2026",
                               organization__name="SSOOrg")
    org = course.organization
    org.email_domain = "sso.example.edu"
    org.sso_enabled = True
    org.sso_provider = "CAS"
    org.sso_config = {"cas_server_url": "https://cas.example.edu/cas/login",
                      "cas_version": "3"}
    org.save()
    return org


@pytest.fixture
def password_user(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        course = CourseFactory(name="cs-pw", period="f2026",
                               organization__name="PwOrg")
    user = course.courseAdmins.first()
    user.set_password("hunter2hunter2")
    user.save()
    return user


class TestNextValidation:

    def test_only_local_authorize_urls_pass(self):
        from core.views.agent_login import validate_next
        assert validate_next(NEXT) == NEXT
        assert validate_next("https://evil.com/o/authorize") is None
        assert validate_next("//evil.com/o/authorize") is None
        assert validate_next("/admin/") is None
        assert validate_next("") is None
        assert validate_next(None) is None


class TestAgentLoginPage:

    def test_get_renders_email_form(self, db):
        resp = Client().get(f"/auth/agent-login/?next={quote(NEXT)}")
        assert resp.status_code == 200
        assert b'name="email"' in resp.content

    def test_password_login_round_trips_to_consent(self, password_user):
        client = Client()
        resp = client.post(f"/auth/agent-login/?next={quote(NEXT)}",
                           {"email": password_user.email,
                            "password": "hunter2hunter2", "next": NEXT})
        assert resp.status_code == 302
        assert resp["Location"] == NEXT
        assert "sessionid" in client.cookies
        # Consent sessions are short-lived, not the two-week default.
        session = client.session
        assert session.get_expiry_age() <= 900

    def test_sso_email_gets_provider_button(self, sso_org):
        resp = Client().post(f"/auth/agent-login/?next={quote(NEXT)}",
                             {"email": "jdoe@sso.example.edu", "next": NEXT})
        assert resp.status_code == 200
        assert b"Continue with CAS" in resp.content
        assert f"org={sso_org.id}".encode() in resp.content
        assert quote(NEXT, safe="").encode() in resp.content

    def test_wrong_password_stays_on_form(self, password_user):
        client = Client()
        resp = client.post(f"/auth/agent-login/?next={quote(NEXT)}",
                           {"email": password_user.email,
                            "password": "wrong", "next": NEXT})
        assert resp.status_code == 200
        assert b"Incorrect email or password" in resp.content
        assert "sessionid" not in client.cookies

    def test_frame_ancestors_locked_down(self, db):
        resp = Client().get("/auth/agent-login/")
        assert resp["Content-Security-Policy"] == "frame-ancestors 'none'"
        resp2 = Client().get("/o/authorize/")
        assert resp2["Content-Security-Policy"] == "frame-ancestors 'none'"


class TestSSOThreading:

    def _callback(self, client, org, *, with_next):
        url = f"/auth/sso/callback/CAS/?org={org.id}&ticket=ST-123"
        if with_next:
            url += f"&next={quote(NEXT, safe='')}"
        with mock.patch("core.views.sso.requests.get") as fake:
            fake.return_value.status_code = 200
            fake.return_value.content = CAS_SUCCESS_XML
            resp = client.get(url)
        return resp, fake

    def test_initiate_threads_next_into_service_url(self, sso_org):
        resp = Client().get(
            f"/auth/sso/login/CAS/?org={sso_org.id}&next={quote(NEXT, safe='')}")
        assert resp.status_code == 302
        location = resp["Location"]
        assert location.startswith("https://cas.example.edu/cas/login?service=")
        # The (doubly-encoded) next rides inside the service URL.
        assert quote(quote(NEXT, safe=""), safe="") in location

    def test_callback_with_next_sets_session_and_redirects_to_consent(
            self, sso_org):
        client = Client()
        resp, fake = self._callback(client, sso_org, with_next=True)
        assert resp.status_code == 302
        assert resp["Location"] == NEXT                 # no JWT in the URL
        assert "sessionid" in client.cookies
        # CAS validation must have used the SAME service URL (with next).
        service = fake.call_args.kwargs["params"]["service"]
        assert quote(NEXT, safe="") in service

    def test_callback_without_next_is_untouched(self, sso_org):
        """The pre-OAuth behaviour, byte-for-byte: JWT redirect, no session."""
        client = Client()
        resp, fake = self._callback(client, sso_org, with_next=False)
        assert resp.status_code == 302
        assert resp["Location"].startswith("http://localhost:3000/?token=")
        assert "sessionid" not in client.cookies
        service = fake.call_args.kwargs["params"]["service"]
        assert "next" not in service

    def test_callback_ignores_open_redirect_next(self, sso_org):
        """A hostile next must not become a redirect target — the login falls
        back to the normal SPA JWT redirect."""
        client = Client()
        url = (f"/auth/sso/callback/CAS/?org={sso_org.id}&ticket=ST-123"
               f"&next={quote('https://evil.com/x', safe='')}")
        with mock.patch("core.views.sso.requests.get") as fake:
            fake.return_value.status_code = 200
            fake.return_value.content = CAS_SUCCESS_XML
            resp = client.get(url)
        assert resp.status_code == 302
        assert resp["Location"].startswith("http://localhost:3000/?token=")
        assert "sessionid" not in client.cookies
