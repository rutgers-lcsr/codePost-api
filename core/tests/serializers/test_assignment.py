# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona

from core.serializers.assignment import *
import unittest


class TestSerializer_AssignmentSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        self.instance_attributes = {
            "name": "Sierpinski",
            "points": 30,
            "isReleased": False,
            "course": self.course
        }

        self.serializer_data = {
            "name": "Nbody",
            "points": 100,
            "isReleased": False,
            "course": self.course.id
        }

        self.instance = Assignment.objects.create(**self.instance_attributes)
        self.serializer = AssignmentSerializer(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = ['id', 'name', 'points', 'isReleased', 'hideGrades', 'course', 'rubricCategories', 'sortKey', 'anonymousGrading', 'hideGradersFromStudents', 'commentFeedback', 'allowStudentUpload',
        #             'uploadDueDate', 'liveFeedbackMode', 'additiveGrading', 'allowRegradeRequests', 'regradeDeadline', 'forcedRubricMode', 'templateMode', 'fileTemplates', 'collaborativeRubricMode', 'testCategories',  'environment']
        # self.assertEqual(set(data.keys()), set(expected))
        pass

    def test_anonymous_grading_course_setting_overridden(self):
        """When anonymousGrading is explicitly set, course default is ignored."""
        self.course.anonymousGradingDefault = True
        self.course.save()
        self.serializer_data["anonymousGrading"] = False
        admin = self.course.courseAdmins.first()
        response = request_as("create", admin, "/assignments/", {
            **self.serializer_data,
            "course": self.course.id,
        })
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["anonymousGrading"])

    def test_anonymous_grading_course_setting_not_overridden(self):
        """When anonymousGrading is not set, course default applies."""
        self.course.anonymousGradingDefault = True
        self.course.save()
        admin = self.course.courseAdmins.first()
        response = request_as("create", admin, "/assignments/", {
            "name": "NewAsg",
            "points": 50,
            "isReleased": False,
            "course": self.course.id,
        })
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["anonymousGrading"])


class TestSerializer_AssignmentSerializerWithStatistics(APITestCase):

    def setUp(self):
        setUpBase(self)

        self.instance_attributes = {
            "name": "Sierpinski",
            "points": 30,
            "isReleased": False,
            "course": self.course
        }

        self.serializer_data = {
            "name": "Nbody",
            "points": 100,
            "isReleased": False,
            "course": self.course.id
        }

        self.instance = Assignment.objects.create(**self.instance_attributes)
        self.serializer = AssignmentSerializerWithStatistics(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = ['id', 'name', 'points', 'isReleased', 'hideGrades', 'course', 'rubricCategories', 'sortKey', 'anonymousGrading', 'hideGradersFromStudents', 'mean', 'median', 'commentFeedback',
        #             'allowStudentUpload', 'uploadDueDate', 'liveFeedbackMode', 'additiveGrading', 'allowRegradeRequests', 'regradeDeadline', 'forcedRubricMode', 'templateMode', 'fileTemplates', 'collaborativeRubricMode',  'testCategories', 'environment']

        # self.assertEqual(set(data.keys()), set(expected))
        pass

    def test_serializer_definition(self):
        base_serializer = AssignmentSerializer(instance=self.instance)
        base_serializer_data = base_serializer.data

        data = self.serializer.data

        diff = set(data.keys()).difference(set(base_serializer_data.keys()))

        self.assertEqual(diff, set(['mean', 'median']))


class TestSerializer_AssignmentStudentSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        self.instance_attributes = {
            "name": "Sierpinski",
            "points": 30,
            "isReleased": False,
            "course": self.course
        }

        self.serializer_data = {
            "name": "Nbody",
            "points": 100,
            "isReleased": False,
            "course": self.course.id
        }

        self.instance = Assignment.objects.create(**self.instance_attributes)
        self.serializer = AssignmentStudentSerializer(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = ['id', 'name', 'isReleased', 'course', 'rubricCategories',
        #             'allowStudentUpload', 'uploadDueDate', 'liveFeedbackMode']
        # self.assertEqual(set(data.keys()), set(expected))
        pass

    def test_serializer_definition(self):
        data = self.serializer.data

        self.assertNotIn('points', data.keys())
        self.assertNotIn('mean', data.keys())
