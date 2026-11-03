# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Regression tests for credential-exposure bugs:

- POST /users/user/ minted tokens for any user to any caller: UserPermissions
  never ran because TemplatePermission.has_permission returns True for a POST
  whose body fails serializer validation (e.g. an empty body).
- UserSerializer.api_token renders the raw DRF Token key (it is the Token's
  primary key), so organizations/{id}/users/ handed org staff every member's key.
- Submission share tokens did not sign their own timestamp, so a holder could
  swap in a fresh one and the 24h expiry never applied.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

import factory
from django.db.models.signals import post_save
from django.utils.http import int_to_base36
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from core.models import User
from core.permissions.tokens import submission_token_generator


def _client_for(user):
  client = APIClient()
  client.force_authenticate(user=user)
  return client


class TestUserLookupEndpoint(APITestCase):

  def setUp(self):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
      self.course = CourseFactory(name="cs100", period="f2025", organization__name="TestOrg")
    self.root = User.objects.create_superuser("root@x.edu", "root@x.edu", "pw")

  def _lookup(self, requester, email):
    return _client_for(requester).post(f"/users/user/?email={email}", {}, format="json")

  def test_student_cannot_mint_tokens_for_a_superuser(self):
    response = self._lookup(self.course.students.first(), self.root.email)
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    self.assertNotIn("refresh", response.data)

  def test_course_admin_cannot_mint_tokens_for_their_student(self):
    student = self.course.students.first()
    response = self._lookup(self.course.courseAdmins.first(), student.email)
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_superuser_lookup_still_works(self):
    student = self.course.students.first()
    response = self._lookup(self.root, student.email)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data["email"], student.email)
    self.assertTrue(response.data["token"])
    self.assertTrue(response.data["refresh"])


class TestApiTokenVisibility(APITestCase):

  def setUp(self):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
      self.course = CourseFactory(name="cs100", period="f2025", organization__name="TestOrg")
    self.org = self.course.organization

    self.staff = self.course.courseAdmins.first()
    self.staff.profile.isOrgStaff = True
    self.staff.profile.organization = self.org
    self.staff.profile.api_token = Token.objects.create(user=self.staff)
    self.staff.profile.save()

    self.victim = self.course.students.first()
    self.victim.profile.organization = self.org
    self.victim.profile.api_token = Token.objects.create(user=self.victim)
    self.victim.profile.save()

  def _org_users(self, requester):
    response = _client_for(requester).get(f"/organizations/{self.org.id}/users/")
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    return {row["email"]: row for row in response.data}

  def test_org_staff_do_not_see_other_members_api_tokens(self):
    rows = self._org_users(self.staff)
    self.assertIsNone(rows[self.victim.email]["api_token"])
    # Their own row still carries their own key.
    self.assertEqual(rows[self.staff.email]["api_token"], self.staff.profile.api_token.key)

  def test_superuser_still_sees_api_tokens(self):
    root = User.objects.create_superuser("root@x.edu", "root@x.edu", "pw")
    rows = self._org_users(root)
    self.assertEqual(rows[self.victim.email]["api_token"], self.victim.profile.api_token.key)

  def test_me_returns_own_api_token(self):
    response = _client_for(self.victim).get("/users/me/")
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data["api_token"], self.victim.profile.api_token.key)


class TestSubmissionShareTokenExpiry(APITestCase):

  def setUp(self):
    self.gen = submission_token_generator
    self.submission = SimpleNamespace(id=42, created=datetime(2024, 1, 1, 12, 0, 0))

  def _at(self, when):
    return mock.patch.object(self.gen, "_now", return_value=when)

  def test_fresh_token_is_valid(self):
    token = self.gen.make_token(self.submission)
    self.assertTrue(self.gen.check_token(self.submission, token))

  def test_token_expires_after_a_day(self):
    token = self.gen.make_token(self.submission)
    with self._at(datetime.now() + timedelta(days=2)):
      self.assertFalse(self.gen.check_token(self.submission, token))

  def test_forged_timestamp_is_rejected(self):
    token = self.gen.make_token(self.submission)
    later = datetime.now() + timedelta(days=30)
    _, mac = token.split("-")
    forged = f"{int_to_base36(self.gen._num_seconds(later))}-{mac}"
    with self._at(later):
      self.assertFalse(self.gen.check_token(self.submission, forged))
