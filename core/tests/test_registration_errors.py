# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Registration / password-reset error paths that used to answer 500: mangled uids in
emailed links, unknown users, and organization-name limits and conflicts."""
from django.contrib.auth.models import User
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Organization

TOKEN = "x" * 24  # the token forms only require min_length=20
PASSWORD = "Rootabega1!"


class TokenLinkErrorTests(APITestCase):

    def test_mangled_uid_is_an_invalid_link_not_a_500(self):
        # "!!" is not base64 at all; "YWJj" decodes to "abc", which is not an id.
        for uid in ("!!not-base64!!", urlsafe_base64_encode(b"abc")):
            for endpoint in ("verifyResetToken", "verifyRegistrationToken"):
                with self.subTest(endpoint=endpoint, uid=uid):
                    resp = self.client.post(f"/registration/{endpoint}/", {"uid": uid, "token": TOKEN})
                    self.assertEqual(resp.status_code, status.HTTP_200_OK)
                    self.assertFalse(resp.data["isValid"])

            with self.subTest(endpoint="handleValidationResponse", uid=uid):
                resp = self.client.get("/registration/handleValidationResponse/", {"uid": uid, "token": TOKEN})
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.assertFalse(resp.data["isValid"])

            with self.subTest(endpoint="registerAndSetPassword", uid=uid):
                resp = self.client.post("/registration/registerAndSetPassword/",
                                        {"uid": uid, "token": TOKEN, "password1": PASSWORD, "password2": PASSWORD})
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(resp.data["isValid"])

            with self.subTest(endpoint="resetPassword", uid=uid):
                resp = self.client.post("/registration/resetPassword/",
                                        {"uid": uid, "token": TOKEN, "password": PASSWORD,
                                         "password1": PASSWORD, "password2": PASSWORD})
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.assertFalse(resp.data["isValid"])

    def test_verify_reset_token_for_unknown_user_is_invalid(self):
        # Used to raise AttributeError (User.ObjectDoesNotExist) → 500.
        uid = urlsafe_base64_encode(force_bytes(999999))
        resp = self.client.post("/registration/verifyResetToken/", {"uid": uid, "token": TOKEN})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, {"isValid": False})


class OrganizationCreationTests(APITestCase):

    def _user_without_password(self):
        return User.objects.create(username="new@example.edu", email="new@example.edu")

    def test_set_credentials_rejects_org_name_over_12_chars(self):
        self.client.force_authenticate(user=self._user_without_password())
        name = "a" * 13
        resp = self.client.post("/registration/setCredentials/",
                                {"organization": name, "password1": PASSWORD, "password2": PASSWORD})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp.data["isValid"])
        self.assertIn("12 characters", resp.data["errors"]["organization"][0])
        self.assertFalse(Organization.objects.filter(name=name).exists())

    def test_set_credentials_reuses_existing_org_by_name(self):
        # shortname differs from the name: the old shortname-only lookup missed it and
        # the create then hit the unique name → IntegrityError → 500.
        org = Organization.objects.create(name="Rutgers", shortname="ru")
        user = self._user_without_password()
        self.client.force_authenticate(user=user)
        resp = self.client.post("/registration/setCredentials/",
                                {"organization": "Rutgers", "password1": PASSWORD, "password2": PASSWORD})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        user.refresh_from_db()
        self.assertEqual(user.profile.organization, org)
        self.assertEqual(Organization.objects.count(), 1)

    def test_validate_new_admin_reuses_existing_org_by_name(self):
        org = Organization.objects.create(name="Rutgers University", shortname="ru")
        resp = self.client.post("/registration/validateNewAdminUser/",
                                {"email": "prof@rutgers.edu", "organization": "Rutgers University"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["action_id"], "2.1.2")
        self.assertFalse(resp.data["is_new_org"])
        self.assertEqual(User.objects.get(email="prof@rutgers.edu").profile.organization, org)
        self.assertEqual(Organization.objects.count(), 1)

    def test_validate_new_admin_rejects_org_name_over_64_chars(self):
        resp = self.client.post("/registration/validateNewAdminUser/",
                                {"email": "prof@rutgers.edu", "organization": "a" * 65})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp.data["success"])
        self.assertIn("64 characters", resp.data["errors"]["organization"][0])
        # Rejected before anything was created.
        self.assertFalse(User.objects.filter(email="prof@rutgers.edu").exists())
        self.assertEqual(Organization.objects.count(), 0)
