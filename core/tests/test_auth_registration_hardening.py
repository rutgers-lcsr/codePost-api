# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Account-state and SSO-flow hardening: a deactivated account stays deactivated through the
reset/activation tokens, the OAuth callback fails cleanly and only for the browser that started
the login, duplicate-email users cannot 500 the login routes, and invite-code joins on a course
without admins answer a clean error. Only the HTTP calls to the IdP are mocked."""
import urllib.parse
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient, APITestCase

from core.models import Course, Organization

PASSWORD = "Rootabega1!"


class DeactivatedAccountTests(APITestCase):

  def _activate(self, user):
    return self.client.post("/registration/registerAndSetPassword/", {
      "uid": urlsafe_base64_encode(force_bytes(user.pk)),
      "token": default_token_generator.make_token(user),
      "password1": PASSWORD, "password2": PASSWORD,
    })

  def test_reset_token_does_not_reactivate_a_deactivated_account(self):
    user = User.objects.create(username="blocked@x.edu", email="blocked@x.edu", is_active=False)
    user.profile.isPasswordSet = True  # had a password: an admin disabled it later
    user.profile.save()
    resp = self._activate(user)
    self.assertEqual(resp.status_code, 400)
    self.assertIsInstance(resp.data["errors"]["token"], str)
    user.refresh_from_db()
    self.assertFalse(user.is_active)
    self.assertFalse(user.check_password(PASSWORD))

  def test_pending_account_is_still_activated(self):
    user = User.objects.create(username="new@x.edu", email="new@x.edu", is_active=False)
    user.profile.isPasswordSet = False
    user.profile.save()
    resp = self._activate(user)
    self.assertEqual(resp.status_code, 200)
    user.refresh_from_db()
    self.assertTrue(user.is_active)
    self.assertTrue(user.check_password(PASSWORD))


class OAuthCallbackTests(APITestCase):

  def setUp(self):
    self.org = Organization.objects.create(
      name="Az Org", shortname="az", email_domain="az.edu", sso_enabled=True, sso_provider="AZURE",
      sso_config={"client_id": "cid", "client_secret": "sec"})

  def _start(self, client):
    resp = client.get(f"/auth/sso/login/AZURE/?org={self.org.id}")
    self.assertEqual(resp.status_code, 302)
    return urllib.parse.parse_qs(urllib.parse.urlparse(resp["Location"]).query)["state"][0]

  def _callback(self, client, state):
    token = MagicMock(status_code=200, json=lambda: {"access_token": "t"})
    me = MagicMock(status_code=200, json=lambda: {"mail": "someone@az.edu"})
    with patch("core.views.sso.requests.post", return_value=token), \
         patch("core.views.sso.requests.get", return_value=me):
      return client.get("/auth/sso/callback/AZURE/", {"org": self.org.id, "code": "c", "state": state})

  def test_happy_path_logs_in(self):
    resp = self._callback(self.client, self._start(self.client))
    self.assertIn("token=", resp["Location"])

  def test_token_exchange_exception_answers_the_generic_sso_failure(self):
    state = self._start(self.client)
    with patch("core.views.sso.requests.post", side_effect=RuntimeError("boom")):
      resp = self.client.get("/auth/sso/callback/AZURE/", {"org": self.org.id, "code": "c", "state": state})
    location = urllib.parse.unquote(resp["Location"])
    self.assertIn("error=", location)
    self.assertIn("An error occurred during SSO authentication", location)
    self.assertNotIn("Could not extract user identity", location)

  def test_state_minted_by_another_browser_is_rejected(self):
    attacker_state = self._start(self.client)
    victim = APIClient()
    resp = self._callback(victim, attacker_state)
    self.assertIn("error=", resp["Location"])
    self.assertNotIn("token=", resp["Location"])
    self.assertFalse(User.objects.filter(email="someone@az.edu").exists())


class DuplicateEmailLoginTests(APITestCase):

  def setUp(self):
    # Django's User.email is not unique; neither row's domain maps to an organization.
    User.objects.create(username="a", email="dup@nowhere.test")
    User.objects.create(username="b", email="dup@nowhere.test")

  def test_initiate_sso_with_duplicate_email_is_not_a_500(self):
    resp = self.client.get("/auth/sso/login/CAS/", {"email": "dup@nowhere.test"})
    self.assertEqual(resp.status_code, 400)

  def test_check_availability_with_duplicate_email_is_not_a_500(self):
    resp = self.client.get("/auth/sso/check/", {"email": "dup@nowhere.test"})
    self.assertEqual(resp.status_code, 200)
    self.assertFalse(resp.json()["sso_enabled"])

  def test_get_or_create_user_refuses_an_ambiguous_identity(self):
    from core.utils import get_or_create_user
    self.assertIsNone(get_or_create_user("dup@nowhere.test", None))

  def test_single_user_whose_domain_maps_nowhere_uses_their_own_organization(self):
    org = Organization.objects.create(
      name="Solo Org", shortname="solo", email_domain="solo.edu", sso_enabled=True, sso_provider="CAS")
    user = User.objects.create(username="solo", email="solo@nowhere-else.test")
    user.profile.organization = org
    user.profile.save()
    resp = self.client.get("/auth/sso/check/", {"email": "solo@nowhere-else.test"})
    self.assertEqual(resp.status_code, 200)
    self.assertEqual(resp.json(), {"sso_enabled": True, "provider": "CAS", "org_id": org.id, "org_name": "Solo Org"})


class InviteCodeWithoutAdminsTests(APITestCase):

  def test_join_with_invite_code_on_course_without_admins_is_a_clean_error(self):
    org = Organization.objects.create(name="Org", shortname="org")
    Course.objects.create(organization=org, name="C1", period="S2026",
                          inviteCode="ABCDEF1234", inviteCodeEnabled=True)
    resp = self.client.post("/registration/emailRegistration/",
                            {"email": "stu@x.edu", "token": "ABCDEF1234"})
    self.assertEqual(resp.status_code, 400)
    self.assertIsInstance(resp.data["detail"], str)
    self.assertFalse(User.objects.filter(email="stu@x.edu").exists())
