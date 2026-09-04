# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Query-count regression test for the staff (non-compact) branch of
GET /assignments/{id}/submissions/.

The base queryset select_relates grader/course and prefetches students, but the
full SubmissionSerializer additionally walks files (+ per-file comments/edit)
and tests. FETCH_PEERS batch-fetches those for the whole result set, so the
query count must not scale with the number of submissions.
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase, APIClient

from core.tests.factories import (
    OrganizationFactory,
    StudentFactory,
    GraderFactory,
    CourseFactory,
    AssignmentFactory,
    SubmissionFactory,
    SubmissionFileFactory,
)


class TestStaffSubmissionsQueryScaling(APITestCase):

  def _hit(self, user, assignment):
    client = APIClient()
    client.force_authenticate(user=user)
    with CaptureQueriesContext(connection) as ctx:
      resp = client.get(f'/assignments/{assignment.id}/submissions/')
    return len(ctx.captured_queries), resp

  def test_submission_count_does_not_scale_query_count(self):
    org = OrganizationFactory()
    course = CourseFactory(name='asubq', period='s2020', organization=org)
    admin = GraderFactory(course='asubq', organization=org, count=600)
    course.courseAdmins.add(admin)
    course.graders.add(admin)

    def build_assignment(name, n_submissions, student_base):
      # AssignmentFactory already creates one submission; reuse it as the first.
      assignment = AssignmentFactory(course=course, name=name, state='published')
      for i in range(n_submissions):
        student = StudentFactory(course='asubq', organization=org, count=student_base + i)
        course.students.add(student)
        sub = assignment.submissions.first() if i == 0 else SubmissionFactory(assignment=assignment)
        sub.students.add(student)
        for j in range(2):
          SubmissionFileFactory(submission=sub, name=f'{name}_{i}_{j}.java')
      return assignment

    a1 = build_assignment('AsubQ-1', 1, 610)
    a4 = build_assignment('AsubQ-4', 4, 620)

    q1, r1 = self._hit(admin, a1)
    q4, r4 = self._hit(admin, a4)

    self.assertEqual(r1.status_code, 200)
    self.assertEqual(r4.status_code, 200)
    self.assertEqual(len(r1.data), 1)
    self.assertEqual(len(r4.data), 4)
    self.assertLessEqual(
        q4, q1 + 2,
        msg=(f"staff submissions endpoint scales with submission count "
             f"({q1} queries for 1 submission, {q4} for 4); FETCH_PEERS may have regressed."),
    )
