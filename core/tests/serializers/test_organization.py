# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import setUpBase
from core.tests.factories import *


class TestSerializer_OrganizationSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass
