# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Query-count regression test for GET /sections/{id}/submissions/?assignment=...

Guards the select_related/prefetch_related on the section submissions action:
the full SubmissionSerializer walks grader, assignment->course, students, files
(+ per-file comments/edit) and tests, so an unprefetched queryset scales by
several queries per submission.
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
    SectionFactory,
    SubmissionFactory,
    SubmissionFileFactory,
)


class TestSectionSubmissionsQueryScaling(APITestCase):

  def _hit(self, user, section, assignment):
    client = APIClient()
    client.force_authenticate(user=user)
    url = f'/sections/{section.id}/submissions/?assignment={assignment.id}'
    with CaptureQueriesContext(connection) as ctx:
      resp = client.get(url)
    return len(ctx.captured_queries), resp

  def test_submission_count_does_not_scale_query_count(self):
    """A section with several multi-file submissions must cost (about) the same number of
    queries as a section with one — relations are prefetched, not loaded per-submission."""
    org = OrganizationFactory()
    course = CourseFactory(name='secq', period='s2020', organization=org)
    grader = GraderFactory(course='secq', organization=org, count=400)
    course.courseAdmins.add(grader)
    course.graders.add(grader)
    assignment = AssignmentFactory(course=course, name='SecQ', state='published')

    # Section A: one student with one single-file submission.
    sectionA = SectionFactory(course=course, name='SecQ-A')
    studentA = StudentFactory(course='secq', organization=org, count=401)
    course.students.add(studentA)
    sectionA.students.add(studentA)
    subA = SubmissionFactory(assignment=assignment)
    subA.students.add(studentA)
    SubmissionFileFactory(submission=subA, name='a0.java')

    # Section B: four students, each with a three-file submission.
    sectionB = SectionFactory(course=course, name='SecQ-B')
    for i in range(4):
      student = StudentFactory(course='secq', organization=org, count=410 + i)
      course.students.add(student)
      sectionB.students.add(student)
      sub = SubmissionFactory(assignment=assignment)
      sub.students.add(student)
      for j in range(3):
        SubmissionFileFactory(submission=sub, name=f'b{i}_{j}.java')

    qA, rA = self._hit(grader, sectionA, assignment)
    qB, rB = self._hit(grader, sectionB, assignment)

    self.assertEqual(rA.status_code, 200)
    self.assertEqual(rB.status_code, 200)
    self.assertEqual(len(rA.data), 1)
    self.assertEqual(len(rB.data), 4)
    # Prefetching makes the cost per extra submission ~0; allow a small fixed margin.
    self.assertLessEqual(
        qB, qA + 2,
        msg=(f"section submissions endpoint scales with submission count "
             f"({qA} queries for 1 submission, {qB} for 4); prefetch may have regressed."),
    )
