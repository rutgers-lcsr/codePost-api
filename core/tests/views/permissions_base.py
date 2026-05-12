# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from parameterized import parameterized


from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona

from core.serializers.assignment import *

OBJECTS = [
    "Assignment",
    "Comment",
    "Course",
    "File",
    "Organization",
    "RubricCategory",
    "RubricComment",
    "Section",
    "Submission"
]

ACTIONS = [
    "Course-roster",
    "Course-courseSettings",
    "Assignment-drawUnassigned",
    "Assignment-rubric",
    "Assignment-submissions",
]


def import_from(module, name):
  module = __import__(module, fromlist=[name])
  return getattr(module, name)

##############################################################################
# ---- InitPermissionsClass -----
#
# Class Naming Convention: TestPermissions_<OBJECT/ACTION_REVERSE>_<MODIFIERDESCRIPTION>
#
# Dictionary of results located in core.tests.permissions.crud.results.<object>
##############################################################################


def initPermissionsClass(self):
  className = self.__class__.__name__
  self.model = "-".join(className.split("_")[1:-1])
  characteristic = className.split("_")[-1]

  results_file = self.model[0].lower() + self.model[1:]
  p = import_from("core.tests.views.results.{}".format(results_file), "PERMISSIONS")
  self.permissions = p["PERMISSIONS_{}".format(characteristic.upper())]
  self.assertIn(self.model, OBJECTS + ACTIONS)


class BaseTestCases:

  class TestPermissions(APITestCase):

    def __init__(self, *args, model="", permissions=None, modifier=None, assertModification=None, **kwargs):
      self.model = model
      self.permissions = permissions if permissions is not None else []
      self.modifier = modifier
      self.assertModification = assertModification
      APITestCase.__init__(self, *args, **kwargs)

    def custom_name_func(testcase_func, param_num, param):
      method = param.args[0]
      persona = param.args[1].name

      description = "{}_as_{}".format(method, persona).lower()

      return "%s_%s" % (
          testcase_func.__name__,
          parameterized.to_safe_name(description),
      )

    def setUp(self):
      # with factory.debug():
      setUpBase(self)

      if self.modifier is not None:
        self.modifier(self)

    actions = []
    for _, persona in enumerate(Persona):
      actions.extend([
          ("create", persona),
          ("read", persona),
          ("update", persona),
          ("delete", persona),
          ("list", persona),
      ])

    @parameterized.expand(actions, name_func=custom_name_func)
    def test_permission(self, method, persona):
      if not (method in self.permissions and persona in self.permissions[method]):
        self.skipTest('permission test not requested')

      if self.model not in self.DB and method == "list":
        self.skipTest('ignored, redundant test')

      user = persona(self)

      detail = None
      if self.model in OBJECTS and self.model in self.DB and method in ['read', 'update', 'delete']:
        detail = self.DB[self.model].id

      if self.model not in OBJECTS:
        detail_model = self.model.split("-")[0]
        detail = self.DB[detail_model].id

      if detail is not None and self.modifier is not None and self.assertModification is not None:
        self.assertModification(self, detail)

      endpoint = None
      if self.model in self.DB:
        if method in ['list', 'create']:
          endpoint = reverse("{}-list".format(self.model.lower()))
        else:
          endpoint = reverse("{}-detail".format(self.model.lower()), args=[detail])
      else:
        route = self.model[0].lower() + self.model[1:]
        endpoint = reverse(route, args=[self.DB["Course"].id])

      payload = None

      if method in ['create'] and 'create' in self.PAYLOADS[self.model]:
        payload = self.PAYLOADS[self.model]['create']
      elif method in ['update'] and 'create' in self.PAYLOADS[self.model]:
        payload = self.PAYLOADS[self.model]['update']
      else:
        payload = {}

      if user is not None:
        response = request_as(method, user, endpoint, payload)
        expected_status = self.permissions[method][persona][0]
        expected_serializer = self.permissions[method][persona][1] if expected_status in [
            status.HTTP_201_CREATED, status.HTTP_200_OK] else None
        self.assertEqual(response.status_code, expected_status)

        # Verify create consistency
        if payload is not None and response.status_code in [status.HTTP_201_CREATED]:
          for key in payload.keys():
            self.assertEqual(response.data[key], payload[key])

        # Verify serializer
        if response.status_code in [status.HTTP_201_CREATED, status.HTTP_200_OK]:
          serializer_fields = expected_serializer.Meta.fields

          if isinstance(response.data, list):
            if len(response.data) > 0:
              response_keys = response.data[0].keys()
            else:
              response_keys = None
          else:
            response_keys = response.data.keys()

          if response_keys is not None:
            self.assertTrue(
                len(set(response_keys).intersection(set(serializer_fields))) > 0,
                "Response shares no fields with expected serializer",
            )
