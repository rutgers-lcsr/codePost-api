# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from core.tests.factories import CourseFactory, OrganizationFactory, UserFactory


class UserListFiltersTests(APITestCase):
  """The staff People page filters /users/ by role and by idleness."""

  def setUp(self):
    org = OrganizationFactory()
    make = lambda email, **kw: UserFactory(username=email, email=email, organization=org, **kw)  # noqa: E731
    self.staff = make('staff@example.com', is_superuser=True, is_staff=True)
    self.course = CourseFactory(organization=org)
    self.student = make('stu@example.com', last_login=timezone.now())
    self.grader = make('gr@example.com', last_login=timezone.now() - timedelta(days=100))
    self.admin = make('ca@example.com', last_login=None)
    self.course.students.add(self.student)
    self.course.graders.add(self.grader)
    self.course.courseAdmins.add(self.admin)
    self.client.force_authenticate(user=self.staff)

  def emails(self, **params):
    response = self.client.get('/users/', params)
    self.assertEqual(response.status_code, 200, response.data)
    return sorted(u['email'] for u in response.data['results'])

  def test_role_filters(self):
    # CourseFactory seeds a roster of its own, so membership is checked, not the whole list.
    students = self.emails(role='student')
    self.assertIn('stu@example.com', students)
    self.assertNotIn('gr@example.com', students)
    self.assertNotIn('ca@example.com', students)
    graders = self.emails(role='grader')
    self.assertIn('gr@example.com', graders)
    self.assertNotIn('stu@example.com', graders)
    admins = self.emails(role='course_admin')
    self.assertIn('ca@example.com', admins)
    self.assertNotIn('stu@example.com', admins)
    self.assertEqual(self.emails(role='platform_admin'), ['staff@example.com'])

  def test_inactive_is_never_or_over_ninety_days(self):
    idle = self.emails(inactive='true')
    self.assertIn('ca@example.com', idle)
    self.assertIn('gr@example.com', idle)
    self.assertNotIn('stu@example.com', idle)
    self.assertNotIn('staff@example.com', self.emails(inactive='1', role='grader'))
    self.assertIn('gr@example.com', self.emails(inactive='1', role='grader'))

  def test_unknown_role_is_a_400_with_detail(self):
    response = self.client.get('/users/', {'role': 'wizard'})
    self.assertEqual(response.status_code, 400)
    self.assertIn('detail', response.data)

  def test_retrieve_by_id_or_email(self):
    by_email = self.client.get(f'/users/{self.grader.email}/')
    by_id = self.client.get(f'/users/{self.grader.id}/')
    self.assertEqual(by_email.status_code, 200, by_email.data)
    self.assertEqual(by_id.status_code, 200, by_id.data)
    self.assertEqual(by_id.data['email'], by_email.data['email'])
    self.assertEqual(self.client.get('/users/999999/').status_code, 404)
    # The list filters never narrow a retrieve.
    self.assertEqual(self.client.get(f'/users/{self.grader.id}/?role=student').status_code, 200)

  def test_retrieve_by_id_needs_staff_or_self(self):
    self.client.force_authenticate(user=self.student)
    self.assertEqual(self.client.get(f'/users/{self.student.id}/').status_code, 200)
    self.assertEqual(self.client.get(f'/users/{self.grader.id}/').status_code, 403)
