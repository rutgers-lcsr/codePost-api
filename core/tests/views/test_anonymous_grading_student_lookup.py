# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
GET /assignments/{id}/submissions/?student=<identity> must not let a grader who is
barred from seeing student identities (anonymous grading) map a student to a submission.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import Assignment, Course, Organization, Submission


class AnonymousGradingStudentLookupTests(APITestCase):
    def setUp(self):
        org = Organization.objects.create(name="Org", shortname="org")
        mk = lambda e: User.objects.create_user(e, e, "pw")
        self.admin, self.grader, self.super, self.student = (
            mk("admin@org.edu"), mk("grader@org.edu"), mk("super@org.edu"), mk("s1@org.edu"))
        self.course = Course.objects.create(name="cs101", period="s2026", organization=org)
        self.course.courseAdmins.add(self.admin)
        self.course.graders.add(self.grader)
        self.course.graders.add(self.super)
        self.course.superGraders.add(self.super)
        self.course.students.add(self.student)
        self.assignment = Assignment.objects.create(
            course=self.course, name="A1", points=10, state='published', anonymousGrading=True)
        self.sub = Submission.objects.create(assignment=self.assignment)
        self.sub.students.add(self.student)

    def _get(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get(f"/assignments/{self.assignment.id}/submissions/?student=s1@org.edu")

    def test_plain_grader_cannot_look_up_student_when_anonymous(self):
        resp = self._get(self.grader)
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_plain_grader_can_look_up_student_when_not_anonymous(self):
        Assignment.objects.filter(id=self.assignment.id).update(anonymousGrading=False)
        resp = self._get(self.grader)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual([s["id"] for s in resp.json()], [self.sub.id])

    def test_admin_and_supergrader_keep_lookup_when_anonymous(self):
        for user in (self.admin, self.super):
            resp = self._get(user)
            self.assertEqual(resp.status_code, 200, (user.email, resp.content))
            self.assertEqual([s["id"] for s in resp.json()], [self.sub.id])

    def test_student_can_still_list_own_submission_when_anonymous(self):
        resp = self._get(self.student)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual([s["id"] for s in resp.json()], [self.sub.id])
