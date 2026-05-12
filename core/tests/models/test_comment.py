# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import setUpBase
from core.tests.factories import *
import unittest


class TestModel_Comment(APITestCase):

    def setUp(self):
        setUpBase(self)

    ########################################
    # Fields
    ########################################

    @unittest.skip('Not implemented yet')
    def test_maximum_pointDelta(self):
        # self.fail('not implemented yet')
        pass

    @unittest.skip('Not implemented yet')
    def test_required_fields(self):
        # self.fail('not implemented yet')
        pass

    ########################################
    # Unique Together
    ########################################

    ########################################
    # Functions
    ########################################

    @unittest.skip('Not implemented yet')
    def test_pointDelta_with_rubricComment(self):
        # self.fail('not implemented yet')
        pass
