from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona

from core.serializers.course import *


class TestSerializer_CourseSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        self.instance_attributes = {
            "name": "COS333",
            "period": "F2020",
            "organization": self.course.organization
        }

        self.serializer_data = {
            "name": "COS333",
            "period": "F2020"
        }

        self.instance = Course.objects.create(**self.instance_attributes)
        self.serializer = CourseSerializer(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = ['id', 'name', 'period', 'assignments', 'sections', 'sendReleasedSubmissionsToBack',
        #             'showStudentsStatistics', 'timezone', 'emailNewUsers', 'anonymousGradingDefault', 'allowGradersToEditRubric']
        # self.assertEqual(set(data.keys()), set(expected))
        pass

    def test_create_course_add_roles(self):
        # self.fail('not implemented yet')
        pass


class TestSerializer_CourseSettingsSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        self.instance_attributes = {
            "name": "COS333",
            "period": "F2020",
            "organization": self.course.organization
        }

        self.serializer_data = {
            "name": "COS333",
            "period": "F2020"
        }

        self.instance = Course.objects.create(**self.instance_attributes)
        self.serializer = CourseSettingsSerializer(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = ['id', 'sendReleasedSubmissionsToBack', 'showStudentsStatistics', 'timezone',
        #             'emailNewUsers', 'anonymousGradingDefault', 'allowGradersToEditRubric']
        # self.assertEqual(set(data.keys()), set(expected))
        pass

    def test_serializer_definition(self):
        base_serializer = CourseSerializer(instance=self.instance)
        base_serializer_data = base_serializer.data

        data = self.serializer.data
        diff = set(data.keys()).difference(set(base_serializer_data.keys()))

        self.assertEqual(set([]), diff)


class TestSerializer_CourseRosterSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        # self.instance_attributes = {
        #     "organization": self.course.organization,
        #     "courseAdmins": self.course.courseAdmins.all()
        #     "students": self.course.students.all(),
        #     "graders": self.course.graders.all(),
        #     "superGraders": self.course.superGraders.all(),
        # }

        # self.serializer_data = {
        #     "organization": self.course.organization,
        #     "courseAdmins": self.course.courseAdmins.all()
        #     "students": self.course.students.all(),
        #     "graders": self.course.graders.all(),
        #     "superGraders": self.course.superGraders.all(),
        # }

        # self.instance =  CourseRoster.objects.create(**self.instance_attributes)
        # self.serializer =  CourseRoster(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = []
        # self.assertEqual(set(data.keys()), set(expected))
        # self.fail('not implemented yet')
        pass

    def test_get_not_activated(self):
        # self.fail('not implemented yet')
        pass

    def test_admin_remove_self_from_roster(self):
        # self.fail('not implemented yet')
        pass

    def test_update_roster(self):
        # self.fail('[PRIORITY] not implemented yet')
        pass
