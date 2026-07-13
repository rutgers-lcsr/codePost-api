# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import setUpBase
from core.tests.factories import *
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
