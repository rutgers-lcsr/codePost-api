# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import setUpBase
from core.tests.factories import *
import unittest


class TestModel_Section(APITestCase):

    def setUp(self):
        setUpBase(self)

    ########################################
    # Fields
    ########################################

    ########################################
    # Unique Together
    ########################################

    @unittest.skip('Not implemented yet')
    def test_create_section_same_name_same_course(self):
        # self.fail('not implemented yet')
        pass

    @unittest.skip('Not implemented yet')
    def test_create_section_same_name_different_course(self):
        # self.fail('not implemented yet')
        pass

    @unittest.skip('Not implemented yet')
    def test_create_section_same_name_same_course_case_sensitive(self):
        # self.fail('not implemented yet')
        pass

    ########################################
    # Functions
    ########################################
