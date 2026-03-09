# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona
import unittest


class TestModel_Organization(APITestCase):

    def setUp(self):
        setUpBase(self)

    ########################################
    # Fields
    ########################################

    @unittest.skip('Not implemented yet')
    def test_create_organization_with_same_name(self):
        # self.fail('not implemented yet')
        pass

    @unittest.skip('Not implemented yet')
    def test_create_organization_with_same_shortname(self):
        # self.fail('not implemented yet')
        pass

    @unittest.skip('Not implemented yet')
    def test_create_organization_with_unique_names(self):
        # self.fail('not implemented yet')
        pass

    ########################################
    # Unique Together
    ########################################

    ########################################
    # Functions
    ########################################
