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
