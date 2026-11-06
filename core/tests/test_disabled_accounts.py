# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""An inactive account is either a pending invitee (not yet activated) or one staff deliberately
disabled. Profile.isDisabled tells them apart: staff deactivation sets it, staff reactivation
clears it, and no automatic activation path (activation/reset link, SSO) may switch a marked
account back on. Only the HTTP calls to the IdP are mocked."""
import urllib.parse
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase

from core.models import Organization
from core.tests.factories import CourseFactory

PASSWORD = "Rootabega1!"


def make_user(email, *, active, disabled=False, org=None, password_set=False, **profile_fields):
  user = User.objects.create(username=email, email=email, is_active=active)
  user.profile.isDisabled = disabled
  user.profile.isPasswordSet = password_set
  user.profile.organization = org
  for field, value in profile_fields.items():
    setattr(user.profile, field, value)
  user.profile.save()
  return user


def link_payload(user):
  return {"uid": urlsafe_base64_encode(force_bytes(user.pk)),
          "token": default_token_generator.make_token(user)}


class ActivationLinkTests(APITestCase):

  def _activate(self, user):
    return self.client.post("/registration/registerAndSetPassword/",
                            {**link_payload(user), "password1": PASSWORD, "password2": PASSWORD})

  def test_disabled_never_activated_account_is_refused(self):
    user = make_user("off@x.edu", active=False, disabled=True)
    resp = self._activate(user)
    self.assertEqual(resp.status_code, 400)
    self.assertIsInstance(resp.data["errors"]["token"], str)
    user.refresh_from_db()
    self.assertFalse(user.is_active)
    self.assertFalse(user.check_password(PASSWORD))

  def test_pending_invitee_still_activates(self):
    user = make_user("new@x.edu", active=False)
    self.assertEqual(self._activate(user).status_code, 200)
    user.refresh_from_db()
    self.assertTrue(user.is_active)
    self.assertTrue(user.check_password(PASSWORD))

  def test_verify_link_reports_a_disabled_account_as_invalid(self):
    user = make_user("off@x.edu", active=False, disabled=True)
    resp = self.client.post("/registration/verifyRegistrationToken/", link_payload(user))
    self.assertEqual(resp.status_code, 200)
    self.assertFalse(resp.data["isValid"])

  def test_verify_link_agrees_with_activation_for_an_inactive_account_that_had_a_password(self):
    """Accounts disabled before the marker existed: the rule registerAndSetPassword already
    applies (inactive + had a password) must not be advertised as a valid link either."""
    user = make_user("old@x.edu", active=False, password_set=True)
    resp = self.client.post("/registration/verifyRegistrationToken/", link_payload(user))
    self.assertFalse(resp.data["isValid"])

  def test_verify_link_accepts_a_pending_invitee(self):
    user = make_user("new@x.edu", active=False)
    resp = self.client.post("/registration/verifyRegistrationToken/", link_payload(user))
    self.assertTrue(resp.data["isValid"])

  def test_reset_password_does_not_activate_a_disabled_account(self):
    user = make_user("off@x.edu", active=False, disabled=True)
    self.client.post("/registration/resetPassword/",
                     {**link_payload(user), "password": PASSWORD, "password2": PASSWORD})
    user.refresh_from_db()
    self.assertFalse(user.is_active)


class SsoLoginTests(APITestCase):
  """get_or_create_user hands back an existing user untouched; SSO must not switch a disabled one on."""

  def setUp(self):
    self.org = Organization.objects.create(
      name="Az Org", shortname="az", email_domain="az.edu", sso_enabled=True, sso_provider="AZURE",
      sso_config={"client_id": "cid", "client_secret": "sec"})

  def _login(self, email):
    start = self.client.get(f"/auth/sso/login/AZURE/?org={self.org.id}")
    state = urllib.parse.parse_qs(urllib.parse.urlparse(start["Location"]).query)["state"][0]
    token = MagicMock(status_code=200, json=lambda: {"access_token": "t"})
    me = MagicMock(status_code=200, json=lambda: {"mail": email})
    with patch("core.views.sso.requests.post", return_value=token), \
         patch("core.views.sso.requests.get", return_value=me):
      return self.client.get("/auth/sso/callback/AZURE/",
                             {"org": self.org.id, "code": "c", "state": state})

  def test_disabled_account_stays_inactive_after_sso_login(self):
    user = make_user("off@az.edu", active=False, disabled=True, org=self.org)
    self._login("off@az.edu")
    user.refresh_from_db()
    self.assertFalse(user.is_active)

  def test_first_sso_login_still_creates_an_active_account(self):
    self._login("fresh@az.edu")
    user = User.objects.get(email="fresh@az.edu")
    self.assertTrue(user.is_active)
    self.assertFalse(user.profile.isDisabled)


class StaffReactivationTests(APITestCase):
  """Every staff path that switches an account on clears the marker."""

  def setUp(self):
    self.org = Organization.objects.create(name="Princeton", shortname="princeton")
    self.superuser = User.objects.create_superuser("super@codepost.io", "super@codepost.io", "SuperPass1!")
    self.pending = make_user("pending@princeton.edu", active=False, disabled=True, org=self.org,
                             pendingValidation=True)

  def _assert_reactivated(self, user=None):
    user = user or self.pending
    user.refresh_from_db()
    self.assertTrue(user.is_active)
    self.assertFalse(user.profile.isDisabled)

  def test_org_approve_admin(self):
    self.client.force_authenticate(self.superuser)
    resp = self.client.post(f"/organizations/{self.org.pk}/approve_admin/", {"user_email": self.pending.email})
    self.assertEqual(resp.status_code, 200)
    self._assert_reactivated()

  def test_org_verify_user_approve(self):
    self.client.force_authenticate(self.superuser)
    resp = self.client.post(f"/organizations/{self.org.pk}/verify_user/",
                            {"user_email": self.pending.email, "action": "approve"})
    self.assertEqual(resp.status_code, 200)
    self._assert_reactivated()

  def test_dashboard_approve_pending_admin(self):
    self.client.force_authenticate(self.superuser)
    resp = self.client.post("/dashboard/approve_pending_admin/", {"user_email": self.pending.email})
    self.assertEqual(resp.status_code, 200)
    self._assert_reactivated()

  def test_validation_link_approve(self):
    resp = self.client.get("/registration/handleValidationResponse/",
                           {**link_payload(self.pending), "activate": "true"})
    self.assertEqual(resp.status_code, 200)
    self._assert_reactivated()

  def test_cip_bulk_activation_skips_disabled_accounts(self):
    """A blanket switch-on of course 925 is not a decision about any one person."""
    # The view hard-codes course 925, and BaseModel.save cannot insert a row with an
    # explicit pk (it treats any pk as an existing row), so hand the view this course.
    course = CourseFactory()
    disabled = make_user("off@x.edu", active=False, disabled=True)
    pending = make_user("new@x.edu", active=False)
    course.students.add(disabled, pending)
    self.client.force_authenticate(self.superuser)
    with patch("core.views.tmp.Course.objects.get", return_value=course):
      self.assertEqual(self.client.post("/tmp-script/").status_code, 200)
    disabled.refresh_from_db()
    pending.refresh_from_db()
    self.assertFalse(disabled.is_active)
    self.assertTrue(disabled.profile.isDisabled)
    self.assertTrue(pending.is_active)


class AdminSiteTests(APITestCase):
  """The Django admin user form is the one place staff flip User.is_active by hand."""

  def setUp(self):
    self.superuser = User.objects.create_superuser("super@codepost.io", "super@codepost.io", "SuperPass1!")
    self.client.force_login(self.superuser)

  def _set_active(self, user, active):
    data = {"username": user.username, "email": user.email, "date_joined_0": "2026-01-01",
            "date_joined_1": "00:00:00"}
    if active:
      data["is_active"] = "on"
    resp = self.client.post(f"/admin/auth/user/{user.pk}/change/", data)
    self.assertEqual(resp.status_code, 302)

  def test_deactivating_marks_and_reactivating_clears(self):
    user = make_user("someone@x.edu", active=True, password_set=True)
    self._set_active(user, False)
    user.refresh_from_db()
    self.assertFalse(user.is_active)
    self.assertTrue(user.profile.isDisabled)
    self._set_active(user, True)
    user.refresh_from_db()
    self.assertTrue(user.is_active)
    self.assertFalse(user.profile.isDisabled)

  def test_saving_other_fields_leaves_a_pending_invitee_unmarked(self):
    user = make_user("new@x.edu", active=False)
    self._set_active(user, False)
    user.refresh_from_db()
    self.assertFalse(user.profile.isDisabled)

  def test_admin_disabled_account_is_refused_by_link_then_works_after_reactivation(self):
    user = make_user("someone@x.edu", active=True)
    self._set_active(user, False)
    payload = {"password1": PASSWORD, "password2": PASSWORD}
    resp = self.client.post("/registration/registerAndSetPassword/", {**link_payload(user), **payload})
    self.assertEqual(resp.status_code, 400)
    self._set_active(user, True)
    resp = self.client.post("/registration/registerAndSetPassword/", {**link_payload(user), **payload})
    self.assertEqual(resp.status_code, 200)
