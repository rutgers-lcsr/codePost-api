# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Authentication at the shell websocket connect handshake.

The environment has no image, so a caller who passes authentication and the
staff check is closed with 4002 ("image missing") before any Docker work.
"""
import sys
import types

# channels.testing imports daphne.testing, which is not installed here.
for _m in ("daphne", "daphne.testing"):
  sys.modules.setdefault(_m, types.ModuleType(_m))
sys.modules["daphne.testing"].DaphneProcess = getattr(sys.modules["daphne.testing"], "DaphneProcess", object)

import factory
import jwt
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.db.models.signals import post_save
from django.test import TransactionTestCase, override_settings
from rest_framework.authtoken.models import Token

from autograder.consumers import EnvironmentShellConsumer
from core.models import Environment
from core.tests.factories import CourseFactory
from core.views.auth import access_token_for_user


@override_settings(DEBUG=False)
class ShellWebsocketAuthTests(TransactionTestCase):
  def setUp(self):
    with factory.django.mute_signals(post_save):
      self.course = CourseFactory()
      assignment = self.course.assignments.first()
      self.env, _ = Environment.objects.get_or_create(assignment=assignment)
    self.admin = self.course.courseAdmins.first()

  def _connect(self, token):
    async def go():
      comm = WebsocketCommunicator(
        EnvironmentShellConsumer.as_asgi(), f"/ws/autograder/environments/{self.env.id}/shell/?token={token}"
      )
      comm.scope["url_route"] = {"kwargs": {"environment_id": self.env.id}}
      _, code = await comm.connect()
      return code
    return async_to_sync(go)()

  def test_active_admin_with_jwt_passes_authentication(self):
    self.assertEqual(self._connect(access_token_for_user(self.admin)), 4002)

  def test_inactive_admin_with_valid_jwt_is_rejected(self):
    token = access_token_for_user(self.admin)
    self.admin.is_active = False
    self.admin.save()
    self.assertEqual(self._connect(token), 4001)

  def test_active_admin_with_drf_token_passes_authentication(self):
    token = Token.objects.create(user=self.admin)
    self.assertEqual(self._connect(token.key), 4002)

  def test_inactive_admin_with_drf_token_is_rejected(self):
    token = Token.objects.create(user=self.admin)
    self.admin.is_active = False
    self.admin.save()
    self.assertEqual(self._connect(token.key), 4001)

  def test_garbage_jwt_is_rejected(self):
    self.assertEqual(self._connect("not.a.jwt"), 4001)

  def test_unsigned_jwt_is_rejected_even_in_debug(self):
    forged = jwt.encode({"user_id": self.admin.id}, "wrong-key", algorithm="HS256")
    with override_settings(DEBUG=True):
      self.assertEqual(self._connect(forged), 4001)
