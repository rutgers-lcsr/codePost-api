from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona


class TestModel_File(APITestCase):

    def setUp(self):
        setUpBase(self)

    ########################################
    # Fields
    ########################################

    ########################################
    # Unique Together
    ########################################

    ########################################
    # Functions
    ########################################

    def test_remove_windows_carriage_returns(self):
        # self.fail('not implemented yet')
        pass
