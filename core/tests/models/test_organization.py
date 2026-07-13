# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import setUpBase
from core.tests.factories import *
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
