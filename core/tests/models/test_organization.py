from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona


class TestModel_Organization(APITestCase):

    def setUp(self):
        setUpBase(self)

    ########################################
    # Fields
    ########################################

    def test_create_organization_with_same_name(self):
        # self.fail('not implemented yet')
        pass

    def test_create_organization_with_same_shortname(self):
        # self.fail('not implemented yet')
        pass

    def test_create_organization_with_unique_names(self):
        # self.fail('not implemented yet')
        pass

    ########################################
    # Unique Together
    ########################################

    ########################################
    # Functions
    ########################################
