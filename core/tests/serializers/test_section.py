from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona


class TestSerializer_SectionSerializer(APITestCase):

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

    def test_add_leaders_and_students(self):
        # self.fail('[PRIORITY] not implemented yet')
        pass
