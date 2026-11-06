# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.test import APITestCase

from core.tests.utils import request_as, setUpBase
from core.tests.factories import *


class TestSubmissionStudentUniqueness(APITestCase):

    def setUp(self):
        setUpBase(self)

    def test_cannot_add_student_who_has_another_submission_on_assignment(self):
        """PATCHing a student onto a submission is rejected when that student already
        has a different submission for the same assignment."""
        sub_a = self.DB["Submission"]
        s0, s1 = list(self.course.students.all())[:2]
        sub_a.students.set([s0])
        sub_b = SubmissionFactory(assignment=sub_a.assignment)
        sub_b.students.set([s1])
        admin = self.course.courseAdmins.first()
        response = request_as("update", admin, f"/submissions/{sub_a.id}/", {
            "students": [s0.email, s1.email],
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("already have submissions", str(response.data))
        self.assertEqual(list(sub_a.students.all()), [s0])
        self.assertEqual(list(sub_b.students.all()), [s1])


class TestSubmissionFinalizeWithoutGrader(APITestCase):

    def setUp(self):
        setUpBase(self)

    def test_finalizing_an_ungraded_submission_is_a_400_not_a_500(self):
        """An unclaimed submission has no grader, so the proposed fields omit it; the
        finalize check must still answer 400 with a message rather than raise KeyError."""
        sub = self.DB["Submission"]
        sub.students.set([self.course.students.first()])
        sub.grader = None
        sub.isFinalized = False
        sub.save()
        admin = self.course.courseAdmins.first()
        response = request_as("update", admin, f"/submissions/{sub.id}/", {"isFinalized": True})
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("must have a grader", str(response.data))
