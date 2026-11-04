# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
GET /courses/ scoping: platform superusers list every course (the staff console audits
them all and compares the list with /dashboard/stats/), while course admins and org
staff keep seeing only the courses they belong to.
"""
from rest_framework.test import APITestCase

from core.tests.factories import AdminFactory, CourseFactory, OrganizationFactory, UserFactory


class CourseListScopeTests(APITestCase):
    def setUp(self):
        self.org_a = OrganizationFactory(name="Org A")
        self.org_b = OrganizationFactory(name="Org B")
        self.course_a = CourseFactory(name="cs101", period="f2026", organization=self.org_a)
        self.course_b = CourseFactory(name="cs201", period="f2026", organization=self.org_b)

        self.admin = AdminFactory(username="admin_a@a.edu", email="admin_a@a.edu", organization=self.org_a)
        self.course_a.courseAdmins.add(self.admin)

        self.superuser = UserFactory(
            username="root@a.edu", email="root@a.edu", organization=self.org_a, is_superuser=True
        )

    def _names(self, resp):
        return sorted(course["name"] for course in resp.json())

    def test_superuser_lists_every_course(self):
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get("/courses/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._names(resp), ["cs101", "cs201"])

    def test_course_admin_lists_only_their_courses(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/courses/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._names(resp), ["cs101"])
