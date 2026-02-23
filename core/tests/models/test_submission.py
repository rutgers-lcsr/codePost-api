# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona


class TestModel_Submission(APITestCase):

    def setUp(self):
        setUpBase(self)

    ########################################
    # Fields
    ########################################

    def test_min_grade(self):
        # self.fail('not implemented yet')
        pass

    ########################################
    # Unique Together
    ########################################

    ########################################
    # Functions
    ########################################

    def test_did_call_calculate_grade_if_frozen(self):
        # self.fail('not implemented yet')
        pass

    def test_did_call_calculate_grade_if_finalized(self):
        # self.fail('not implemented yet')
        pass

    def test_did_call_calculate_grade_if_frozen_and_finalized(self):
        # self.fail('not implemented yet')
        pass

    def test_calculate_grade_getCurrentFiles_with_path(self):
        # self.fail('not implemented yet')
        pass

    def test_calculate_grade_getCurrentFiles_without_path(self):
        # self.fail('not implemented yet')
        pass

    def test_calculate_grade_parameterized(self):
        # self.fail('not implemented yet')
        pass
