from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona


class TestModel_Section(APITestCase):

    def setUp(self):
        setUpBase(self)

    ########################################
    # Fields
    ########################################

    ########################################
    # Unique Together
    ########################################

    def test_create_section_same_name_same_course(self):
        # self.fail('not implemented yet')
        pass

    def test_create_section_same_name_different_course(self):
        # self.fail('not implemented yet')
        pass

    def test_create_section_same_name_same_course_case_sensitive(self):
        # self.fail('not implemented yet')
        pass

    ########################################
    # Functions
    ########################################
