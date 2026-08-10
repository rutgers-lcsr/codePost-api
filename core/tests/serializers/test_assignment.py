# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *

from core.serializers.assignment import *


class TestSerializer_AssignmentSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        self.instance_attributes = {
            "name": "Sierpinski",
            "points": 30,
            "state": "preview",
            "course": self.course
        }

        self.serializer_data = {
            "name": "Nbody",
            "points": 100,
            "state": "preview",
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
            "state": "preview",
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
            "state": "preview",
            "course": self.course
        }

        self.serializer_data = {
            "name": "Nbody",
            "points": 100,
            "state": "preview",
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
            "state": "preview",
            "course": self.course
        }

        self.serializer_data = {
            "name": "Nbody",
            "points": 100,
            "state": "preview",
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


class TestStudentReleasedSerializersLeakGuard(APITestCase):
    """The post-feedback student serializers must expose exactly the student base plus
    STUDENT_RELEASED_EXTRA_FIELDS — staff-only fields (AI prompts, grading internals)
    must never re-enter the student payload. (The persona matrix harness only checks a
    key intersection, so this is the real guard.)"""

    STAFF_ONLY_FIELDS = (
        'ai_system_prompt', 'ai_summary_prompt', 'ai_description', 'ai_description_locked',
        'anonymousGrading', 'hideGradersFromStudents', 'testCategories',
        'showFrequentlyUsedRubricComments', 'forcedRubricMode', 'templateMode',
        'collaborativeRubricMode', 'gradersCanEditSubmissions',
        'runFilesOnSubmit', 'runTestsOnSubmit',
    )

    def setUp(self):
        setUpBase(self)
        self.assignment = Assignment.objects.get(id=self.DB['Assignment'].id)
        self.assignment.state = 'published'
        self.assignment.feedbackReleased = True
        self.assignment.save()

    def test_no_stats_field_set_is_exactly_base_plus_extras(self):
        expected = set(AssignmentSerializerBase.Meta.fields) | set(STUDENT_RELEASED_EXTRA_FIELDS)
        self.assertEqual(set(AssignmentStudentSerializerNoStats.Meta.fields), expected)

    def test_with_stats_adds_only_mean_median(self):
        self.assertEqual(
            set(AssignmentStudentSerializerWithStats.Meta.fields)
            - set(AssignmentStudentSerializerNoStats.Meta.fields),
            {'mean', 'median'})

    def test_staff_fields_absent_and_student_fields_present(self):
        for serializer_class in (AssignmentStudentSerializerNoStats,
                                 AssignmentStudentSerializerWithStats):
            data = serializer_class(instance=self.assignment).data
            for field in self.STAFF_ONLY_FIELDS:
                self.assertNotIn(field, data, f"{serializer_class.__name__} leaks {field}")
            self.assertIn('explanation', data)
            for field in STUDENT_RELEASED_EXTRA_FIELDS:
                self.assertIn(field, data, f"{serializer_class.__name__} missing {field}")
        self.assertNotIn('mean', AssignmentStudentSerializerNoStats(instance=self.assignment).data)

    def test_student_retrieve_has_no_staff_fields(self):
        from django.urls import reverse
        from core.tests.views.personas import Persona
        from rest_framework import status as drf_status

        student = Persona.STUDENT_OF_COURSE(self)
        endpoint = reverse("assignment-detail", args=[self.assignment.id])

        response = request_as('read', student, endpoint)
        self.assertEqual(response.status_code, drf_status.HTTP_200_OK)
        # camelCase over the wire (djangorestframework-camel-case)
        self.assertNotIn('aiSystemPrompt', response.data)
        self.assertNotIn('anonymousGrading', response.data)
        self.assertIn('points', response.data)
        self.assertIn('explanation', response.data)
        self.assertNotIn('mean', response.data)  # course stats off by default

        self.course.showStudentsStatistics = True
        self.course.save()
        response = request_as('read', student, endpoint)
        self.assertIn('mean', response.data)
        self.assertNotIn('aiSystemPrompt', response.data)
