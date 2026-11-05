# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""POST /users/{email}/email/: a malformed or foreign `assignment` is a client error, never a 500."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import Assignment, Course, Organization


class UserEmailAssignmentLookupTests(APITestCase):
    def setUp(self):
        org = Organization.objects.create(name="Org", shortname="org")
        self.student = User.objects.create_user("student@org.edu", "student@org.edu", "pw")
        self.admin = User.objects.create_user("admin@org.edu", "admin@org.edu", "pw")
        self.course = Course.objects.create(name="cs101", period="s2026", organization=org)
        self.course.courseAdmins.add(self.admin)
        self.course.students.add(self.student)
        self.assignment = Assignment.objects.create(
            course=self.course, name="A1", points=20, state='published')
        other = Course.objects.create(name="cs102", period="s2026", organization=org)
        self.foreign_assignment = Assignment.objects.create(
            course=other, name="B1", points=20, state='published')
        self.client.force_authenticate(user=self.admin)

    def _post(self, assignment):
        return self.client.post(
            f"/users/{self.student.email}/email/",
            {"course": self.course.id, "assignment": assignment, "template": "publish_assignment"},
            format="json")

    def test_non_numeric_assignment_is_400(self):
        resp = self._post("abc")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIsInstance(resp.json()["detail"], str)

    def test_list_valued_assignment_is_400(self):
        resp = self._post([1, 2])
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIsInstance(resp.json()["detail"], str)

    def test_unknown_assignment_is_404(self):
        resp = self._post(999999)
        self.assertEqual(resp.status_code, 404, resp.content)
        self.assertIsInstance(resp.json()["detail"], str)

    def test_assignment_of_another_course_is_404(self):
        resp = self._post(self.foreign_assignment.id)
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_assignment_of_this_course_is_accepted(self):
        resp = self._post(self.assignment.id)
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_invalid_template_is_400_with_detail(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            f"/users/{self.student.email}/email/",
            {"course": self.course.id, "template": "nope"}, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIsInstance(resp.json()["detail"], str)

    def test_duplicate_email_resolves_to_the_course_member(self):
        User.objects.create_user("dup2", self.student.email, "pw")
        resp = self._post(self.assignment.id)
        self.assertEqual(resp.status_code, 200, resp.content)
