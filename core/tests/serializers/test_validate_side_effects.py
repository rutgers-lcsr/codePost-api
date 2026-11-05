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


class TestSubmissionLateDayAudit(APITestCase):

    def setUp(self):
        setUpBase(self)
        self.sub = self.DB["Submission"]
        self.sub.students.set(list(self.course.students.all())[:2])
        self.course.lateDayCreditsAllowable = 5
        self.course.save()
        self.admin = self.course.courseAdmins.first()
        self.url = f"/submissions/{self.sub.id}/"

    def _events(self):
        return CourseAuditEvent.objects.filter(course=self.course, event_type="late_day_used").count()

    def test_unrelated_patch_records_no_late_day_event(self):
        self.sub.lateDayCreditsUsed = 2
        self.sub.save()
        response = request_as("update", self.admin, self.url, {"queueOrderKey": 99})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._events(), 0)

    def test_unrelated_patch_not_blocked_after_allowance_lowered(self):
        self.sub.lateDayCreditsUsed = 4
        self.sub.save()
        self.course.lateDayCreditsAllowable = 1
        self.course.save()
        response = request_as("update", self.admin, self.url, {"queueOrderKey": 99})
        self.assertEqual(response.status_code, 200, response.data)

    def test_changing_credits_records_event_once_per_student(self):
        n_students = self.sub.students.count()
        response = request_as("update", self.admin, self.url, {"lateDayCreditsUsed": 2})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._events(), n_students)

    def test_over_allowance_still_rejected_and_no_event(self):
        response = request_as("update", self.admin, self.url, {"lateDayCreditsUsed": 9})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._events(), 0)

    def test_failed_save_leaves_no_event(self):
        with mock.patch.object(ModelSerializer, "update", side_effect=IntegrityError("boom")):
            request_as("update", self.admin, self.url, {"lateDayCreditsUsed": 2})
        self.assertEqual(self._events(), 0)

    def _second_assignment(self):
        return AssignmentFactory(course=self.course, name="Second", submissions=None)

    def test_single_credit_over_exhausted_allowance_rejected(self):
        self.course.lateDayCreditsAllowable = 0
        self.course.save()
        response = request_as("update", self.admin, self.url, {"lateDayCreditsUsed": 1})
        self.assertEqual(response.status_code, 400)

    def test_single_credit_records_event(self):
        response = request_as("update", self.admin, self.url, {"lateDayCreditsUsed": 1})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._events(), self.sub.students.count())

    def test_resetting_credits_to_zero_records_no_event_and_is_not_blocked(self):
        # Another submission already exceeds the lowered allowance for these students.
        other = SubmissionFactory(assignment=self._second_assignment(), lateDayCreditsUsed=3)
        other.students.set(self.sub.students.all())
        self.sub.lateDayCreditsUsed = 2
        self.sub.save()
        self.course.lateDayCreditsAllowable = 1
        self.course.save()
        response = request_as("update", self.admin, self.url, {"lateDayCreditsUsed": 0})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._events(), 0)

    def test_no_event_when_course_has_no_late_day_allowance(self):
        self.course.lateDayCreditsAllowable = None
        self.course.save()
        response = request_as("update", self.admin, self.url, {"lateDayCreditsUsed": 2})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._events(), 0)

    def test_resending_same_assignment_is_not_a_credit_change(self):
        self.sub.lateDayCreditsUsed = 4
        self.sub.save()
        self.course.lateDayCreditsAllowable = 1
        self.course.save()
        response = request_as("update", self.admin, self.url, {"assignment": self.sub.assignment_id})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._events(), 0)

    def test_creating_submission_over_allowance_rejected(self):
        self.course.lateDayCreditsAllowable = 1
        self.course.save()
        student = self.course.students.first()
        response = request_as("create", self.admin, "/submissions/", {
            "assignment": self._second_assignment().id, "students": [student.username], "lateDayCreditsUsed": 3})
        self.assertEqual(response.status_code, 400, response.content)

    def test_creating_submission_with_credits_records_event(self):
        student = self.course.students.first()
        response = request_as("create", self.admin, "/submissions/", {
            "assignment": self._second_assignment().id, "students": [student.username], "lateDayCreditsUsed": 2})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self._events(), 1)
