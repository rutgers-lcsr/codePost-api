# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *

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
        """Creating a course auto-adds the creator as courseAdmin and grader."""
        admin = self.course.courseAdmins.first()
        response = request_as("create", admin, "/courses/", {
            "name": "NewCourse",
            "period": "F2025",
        })
        self.assertEqual(response.status_code, 201)
        from core.models import Course as CourseModel
        new_course = CourseModel.objects.get(id=response.data["id"])
        self.assertIn(admin, new_course.courseAdmins.all())
        self.assertIn(admin, new_course.graders.all())


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
        """not_activated returns inactive users."""
        admin = self.course.courseAdmins.first()
        response = request_as("read", admin, f"/courses/{self.course.id}/roster/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("not_activated", response.data)

    def test_admin_remove_self_from_roster(self):
        """Admin cannot remove themselves from courseAdmins."""
        admin = self.course.courseAdmins.first()
        other_admins = [a.email for a in self.course.courseAdmins.all() if a != admin]
        response = request_as("update", admin, f"/courses/{self.course.id}/roster/", {
            "courseAdmins": other_admins,
            "graders": [g.email for g in self.course.graders.all()],
            "students": [s.email for s in self.course.students.all()],
            "superGraders": [sg.email for sg in self.course.superGraders.all()],
            "rubricEditors": [re.email for re in self.course.rubricEditors.all()],
        })
        self.assertEqual(response.status_code, 400)

    def test_update_roster(self):
        """Can update roster with valid data."""
        admin = self.course.courseAdmins.first()
        response = request_as("update", admin, f"/courses/{self.course.id}/roster/", {
            "courseAdmins": [a.email for a in self.course.courseAdmins.all()],
            "graders": [g.email for g in self.course.graders.all()],
            "students": [s.email for s in self.course.students.all()],
            "superGraders": [sg.email for sg in self.course.superGraders.all()],
            "rubricEditors": [re.email for re in self.course.rubricEditors.all()],
        })
        self.assertEqual(response.status_code, 200)
