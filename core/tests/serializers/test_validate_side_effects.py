# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Roster / submission / assignment / prompt-variant serializers: no side effects in
validate(), correct scoping of the self-removal guard, and 400 (not 500) on bad input."""
from unittest import mock

from django.db import IntegrityError
from rest_framework.serializers import ModelSerializer
from rest_framework.test import APITestCase

from core.models import CourseAuditEvent
from core.serializers.course import CourseRosterSerializer
from core.tests.factories import *
from core.tests.utils import request_as, setUpBase


class TestRosterPatch(APITestCase):

    def setUp(self):
        setUpBase(self)

    def _outsider(self, name, **flags):
        user = UserFactory(username=f"{name}@princeton.edu", organization=self.course.organization)
        if flags.pop("is_superuser", False):
            user.is_superuser = True
            user.save()
        for k, v in flags.items():
            setattr(user.profile, k, v)
        user.profile.save()
        return user

    def test_superuser_who_is_not_course_admin_can_patch_roster(self):
        su = self._outsider("root", is_superuser=True)
        student = self.course.students.first()
        response = request_as("update", su, f"/courses/{self.course.id}/roster/",
                              {"students": [student.email]})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(self.course.students.all()), [student])
        self.assertFalse(self.course.courseAdmins.filter(pk=su.pk).exists())

    def test_admin_still_cannot_remove_self(self):
        admin = self.course.courseAdmins.first()
        others = [a.email for a in self.course.courseAdmins.all() if a != admin]
        response = request_as("update", admin, f"/courses/{self.course.id}/roster/",
                              {"courseAdmins": others})
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot remove itself", str(response.data))

    def test_section_membership_untouched_when_update_fails(self):
        section = self.DB["Section"]
        s1, s2 = list(self.course.students.all())[:2]
        section.students.set([s1, s2])
        admin = self.course.courseAdmins.first()
        with mock.patch.object(ModelSerializer, "update", side_effect=IntegrityError("boom")):
            response = request_as("update", admin, f"/courses/{self.course.id}/roster/",
                                  {"students": [s1.email]})
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(set(section.students.all()), {s1, s2})

    def test_section_membership_pruned_on_successful_update(self):
        section = self.DB["Section"]
        s1, s2 = list(self.course.students.all())[:2]
        g = self.course.graders.first()
        section.students.set([s1, s2])
        section.leaders.set([g])
        admin = self.course.courseAdmins.first()
        response = request_as("update", admin, f"/courses/{self.course.id}/roster/",
                              {"students": [s1.email], "graders": []})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(section.students.all()), [s1])
        self.assertEqual(list(section.leaders.all()), [])
