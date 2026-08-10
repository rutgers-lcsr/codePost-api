# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Query-count regression tests for the student dashboard data path.

These guard the two N+1s fixed for dashboard load time:
- GET /users/me/ must not fan out ~20 queries per enrolled course.
- GET /assignments/{id}/submissions/?student=... must not fan out one query per file.
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase, APIClient

from core.tests.factories import (
    OrganizationFactory,
    StudentFactory,
    CourseFactory,
    AssignmentFactory,
    SubmissionFileFactory,
)


class TestUsersMeQueryScaling(APITestCase):
  endpoint = '/users/me/'

  def _count_me_queries(self, student):
    client = APIClient()
    client.force_authenticate(user=student)
    with CaptureQueriesContext(connection) as ctx:
      resp = client.get(self.endpoint)
    return len(ctx.captured_queries), resp

  def test_query_count_is_bounded_per_enrolled_course(self):
    """Enrolling a student in more courses must not add ~20 queries per course.

    Before prefetching, each nested CourseSerializer cost ~20 queries (capabilities,
    get_assignments role checks, studentCount, sections, webhooks). With the role M2Ms
    and course sub-relations prefetched on /users/me, the per-course cost is near zero.
    """
    org = OrganizationFactory()

    # Student A: enrolled in 1 course.
    studentA = StudentFactory(course='qa', organization=org, count=100)
    courseA = CourseFactory(name='qcourse_a0', period='s2020', organization=org)
    courseA.students.add(studentA)

    # Student B: enrolled in 4 identically-structured courses.
    studentB = StudentFactory(course='qb', organization=org, count=101)
    for i in range(4):
      course = CourseFactory(name=f'qcourse_b{i}', period='s2020', organization=org)
      course.students.add(studentB)

    qA, respA = self._count_me_queries(studentA)
    qB, respB = self._count_me_queries(studentB)

    self.assertEqual(respA.status_code, 200)
    self.assertEqual(respB.status_code, 200)
    self.assertEqual(len(respA.data['studentCourses']), 1)
    self.assertEqual(len(respB.data['studentCourses']), 4)

    per_course = (qB - qA) / 3.0
    self.assertLess(
        per_course, 6.0,
        msg=(f"/users/me scales ~{per_course:.1f} queries per course "
             f"(A={qA} with 1 course, B={qB} with 4); prefetch may have regressed."),
    )


class TestStudentSubmissionsFilesQueryCount(APITestCase):

  def _hit(self, student, assignment):
    client = APIClient()
    client.force_authenticate(user=student)
    url = f'/assignments/{assignment.id}/submissions/?student={student.email}&compact=1'
    with CaptureQueriesContext(connection) as ctx:
      resp = client.get(url)
    return len(ctx.captured_queries), resp

  def test_file_count_does_not_change_query_count(self):
    """A submission with many files must cost the same number of queries as one with a
    single file — i.e. files are prefetched rather than loaded per-file."""
    org = OrganizationFactory()
    course = CourseFactory(name='subq', period='s2020', organization=org)
    student = StudentFactory(course='subq', organization=org, count=200)
    course.students.add(student)

    # Assignment 1: submission has the single file created by the factory.
    a1 = AssignmentFactory(course=course, name='One File', isReleased=True)
    s1 = a1.submissions.first()
    s1.students.add(student)

    # Assignment 2: submission has five files.
    a2 = AssignmentFactory(course=course, name='Many Files', isReleased=True)
    s2 = a2.submissions.first()
    s2.students.add(student)
    for i in range(4):
      SubmissionFileFactory(submission=s2, name=f'extra_{i}.java')

    q1, r1 = self._hit(student, a1)
    q2, r2 = self._hit(student, a2)

    self.assertEqual(r1.status_code, 200)
    self.assertEqual(r2.status_code, 200)
    self.assertEqual(len(r1.data[0]['files']), 1)
    self.assertEqual(len(r2.data[0]['files']), 5)
    self.assertLessEqual(
        q2, q1,
        msg=(f"submissions endpoint scales with file count ({q1} query for 1 file, "
             f"{q2} for 5); files may not be prefetched."),
    )


class TestHideFromQueryScaling(APITestCase):
  """The server-side hideFrom filter in CourseSerializer.get_assignments adds one bounded
  query per course for students — it must not scale with the number of assignments or
  hideFrom rows."""
  endpoint = '/users/me/'

  def _count_me_queries(self, student):
    client = APIClient()
    client.force_authenticate(user=student)
    with CaptureQueriesContext(connection) as ctx:
      resp = client.get(self.endpoint)
    return len(ctx.captured_queries), resp

  def test_hidefrom_does_not_scale_per_assignment(self):
    from core.tests.factories import SectionFactory
    org = OrganizationFactory()

    # Student A: course with 1 assignment carrying a hideFrom row.
    studentA = StudentFactory(course='hfa', organization=org, count=300)
    courseA = CourseFactory(name='hf_course_a', period='s2020', organization=org)
    courseA.students.add(studentA)
    sectionA = SectionFactory(course=courseA, name='HF-A')
    a = AssignmentFactory(course=courseA, name='hf-a-0', state='published')
    a.hideFrom.add(sectionA)

    # Student B: course with 5 assignments, each carrying a hideFrom row.
    studentB = StudentFactory(course='hfb', organization=org, count=301)
    courseB = CourseFactory(name='hf_course_b', period='s2020', organization=org)
    courseB.students.add(studentB)
    sectionB = SectionFactory(course=courseB, name='HF-B')
    for i in range(5):
      assignment = AssignmentFactory(course=courseB, name=f'hf-b-{i}', state='published')
      assignment.hideFrom.add(sectionB)

    qA, respA = self._count_me_queries(studentA)
    qB, respB = self._count_me_queries(studentB)

    self.assertEqual(respA.status_code, 200)
    self.assertEqual(respB.status_code, 200)
    self.assertLessEqual(
        qB, qA,
        msg=(f"hideFrom filtering scales with assignment count ({qA} queries for 1 "
             f"assignment, {qB} for 5); it must stay one bounded query per course."),
    )
