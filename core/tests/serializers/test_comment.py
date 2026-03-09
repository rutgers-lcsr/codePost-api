# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *
from core.tests.views.personas import Persona

from core.serializers.comment import *

from parameterized import parameterized, parameterized_class
import unittest


class TestSerializer_CommentSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        self.instance_attributes = {
            "text": "# Correct!",
            "pointDelta": 2,
            "author": self.course.courseAdmins.first(),
            "file": self.course.assignments.first().submissions.first().files.first(),
            "startLine": 0,
            "endLine": 10,
            "startChar": 0,
            "endChar": 5,
        }

        self.serializer_data = {
            "text": "# Correct!",
            "pointDelta": 2,
            "author": self.course.courseAdmins.first(),
            "file": self.course.assignments.first().submissions.first().files.first().id,
            "startLine": 0,
            "endLine": 10,
            "startChar": 0,
            "endChar": 5,
        }

        self.instance = Comment.objects.create(**self.instance_attributes)
        self.serializer = CommentSerializer(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = ['id', 'text', 'pointDelta', 'startChar', 'endChar', 'startLine',
        #             'endLine', 'file', 'rubricComment', 'author', 'feedback', 'color']
        # self.assertEqual(set(data.keys()), set(expected
        pass

    @parameterized.expand([("startLine",), ("endLine",), ("startChar",), ("endChar",)])
    def test_validate_positive_indices(self, field):
        self.serializer_data[field] = -1
        serializer = CommentSerializer(data=self.serializer_data)

        self.assertFalse(serializer.is_valid())
        self.assertEqual(set(serializer.errors), set([field]))

    def test_validate_line_order(self):
        self.serializer_data["startLine"] = 5
        self.serializer_data["endLine"] = 3
        serializer = CommentSerializer(data=self.serializer_data)

        self.assertFalse(serializer.is_valid())

    def test_validate_char_order_same_line(self):
        self.serializer_data["startLine"] = 5
        self.serializer_data["endLine"] = 5
        self.serializer_data["startChar"] = 10
        self.serializer_data["endChar"] = 5
        serializer = CommentSerializer(data=self.serializer_data)

        self.assertFalse(serializer.is_valid())

    def test_validate_char_order_diff_line(self):
        self.serializer_data["startLine"] = 5
        self.serializer_data["endLine"] = 6
        self.serializer_data["startChar"] = 10
        self.serializer_data["endChar"] = 5
        serializer = CommentSerializer(data=self.serializer_data)

        self.assertTrue(serializer.is_valid())

    def test_color_hexadecimal_valid(self):
        """Valid hex color passes validation."""
        color_data = self.serializer_data.copy()
        color_data["color"] = "#FF0000"
        color_data["endLine"] = 0
        serializer = CommentSerializer(data=color_data, context={"request": type("Req", (), {"user": self.course.courseAdmins.first()})})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_color_hexadecimal_invalid(self):
        """Invalid hex color fails validation."""
        self.serializer_data["color"] = "not-a-color"
        serializer = CommentSerializer(data=self.serializer_data, context={"request": type("Req", (), {"user": self.course.courseAdmins.first()})})
        self.assertFalse(serializer.is_valid())

    def test_set_comment_author(self):
        # set grader from other course
        # check permissions on set grader
        # self.fail('[PRIORITY] not implemented yet')
        pass


class TestSerializer_CommentBasicSerializer(APITestCase):

    def setUp(self):
        setUpBase(self)

        self.instance_attributes = {
            "text": "# Correct!",
            "pointDelta": 2,
            "author": self.course.courseAdmins.first(),
            "file": self.course.assignments.first().submissions.first().files.first(),
            "startLine": 0,
            "endLine": 10,
            "startChar": 0,
            "endChar": 5,
        }

        self.serializer_data = {
            "text": "# Correct!",
            "pointDelta": 2,
            "author": self.course.courseAdmins.first(),
            "file": self.course.assignments.first().submissions.first().files.first().id,
            "startLine": 0,
            "endLine": 10,
            "startChar": 0,
            "endChar": 5,
        }

        self.instance = Comment.objects.create(**self.instance_attributes)
        self.serializer = CommentBasicSerializer(instance=self.instance)

    def test_contains_expected_fields(self):
        # data = self.serializer.data

        # expected = ['id', 'text', 'pointDelta', 'startChar', 'endChar',
        #             'startLine', 'endLine', 'file', 'rubricComment', 'feedback']
        # self.assertEqual(set(data.keys()), set(expected))
        pass

    def test_serializer_definition(self):
        base_serializer = CommentSerializer(instance=self.instance)
        base_serializer_data = base_serializer.data

        data = self.serializer.data
        diff = set(base_serializer_data.keys()).difference(set(data.keys()))

        self.assertIn('author', diff)
