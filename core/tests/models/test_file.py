# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona
import unittest


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

    @unittest.skip('Not implemented yet')
    def test_remove_windows_carriage_returns(self):
        # self.fail('not implemented yet')
        pass
