from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona


class TestSerializer_SubmissionSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass

    def test_queue_ordering_on_update(self):
        # self.fail('[PRIORITY] not implemented yet')
        pass

    def test_date_edited_format(self):
        # self.fail('[PRIORITY] not implemented yet')
        pass

    def test_update_students(self):
        # self.fail('[PRIORITY] not implemented yet')
        pass

    def test_update_grader(self):
        # self.fail('[PRIORITY] not implemented yet')
        pass

    def test_empty_student_list(self):
        # self.fail('[PRIORITY] not implemented yet')
        pass

    def test_finalize_with_no_grade(self):
        # self.fail('[PRIORITY] not implemented yet')
        pass


class TestSerializer_SubmissionSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass


class TestSerializer_AnonymousSubmissionSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass


class TestSerializer_SubmissionStatusSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass


class TestSerializer_StudentSubmissionSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass


class TestSerializer_StudentSubmissionWithoutGradeSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {

        # }

        # self.serializer_data = {

        # }

        # self.instance = ##.objects.create(**self.instance_attributes)
        # self.serializer = ##(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass
