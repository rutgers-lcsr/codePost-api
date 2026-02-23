# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth.models import User
from core.models import *
from core.serializers.assignment import AssignmentSerializer

# Test Cases (in order of logic in registration.py)

# 1 User Exists
# 1.1 Selected organization does not match User organization
# 1.2.1 User is active and is an admin
# 1.2.2.1 User can be auto approved
# 1.2.2.2 User cannot be auto approved

# 2 New User
# 2.1 Selected organization already exists
# 2.1.1 User is active and is an admin
# 2.1.2.1 User can be auto approved
# 2.1.2.2 User cannot be auto approved
# 2.2 Selected organization does not exist
# 2.2.1 User is active and is an admin
# 2.2.2.1 User can be auto approved
# 2.2.2.2 User cannot be auto approved

# 3 Unknown error


class TestRegistration(APITestCase):

  def setUp(self):
    self.organization = Organization.objects.create(
        name="Princeton", shortname="princeton")
    self.admin = User.objects.create(
        username='admin@princeton.edu', email='admin@princeton.edu', password="Rootabega1!")
    self.course = Course.objects.create(
        organization=self.organization, period="S2019", name="COS126")
    self.admin.profile.organization = self.organization
    self.admin.profile.canCreateCourses = True
    self.admin.profile.canModifyRosters = True
    self.admin.is_staff = True
    self.admin.save()
    self.course.courseAdmins.add(self.admin)
    self.course.save()

  def test_case_11(self):
    payload = {'email': 'admin@princeton.edu', 'organization': 'acu'}
    response = self.client.post(
        '/registration/validateNewAdminUser/', payload)
    self.assertEqual(response.data['action_id'], '1.1')

  def test_case_121(self):
    admin2 = User.objects.create(
        username='admin2@princeton.edu', email='admin2@princeton.edu', password="Rootabega1!")
    admin2.profile.organization = self.organization
    admin2.profile.canCreateCourses = True
    admin2.profile.canModifyRosters = True
    admin2.is_staff = True
    admin2.save()

    payload = {'email': 'admin2@princeton.edu', 'organization': 'princeton'}
    response = self.client.post(
        '/registration/validateNewAdminUser/', payload)
    self.assertEqual(response.data['action_id'], '1.2.1')

  def test_case_1221(self):
    user2 = User.objects.create(
        username='user2@princeton.edu', email='user2@princeton.edu', password="Rootabega1!")
    user2.profile.organization = self.organization
    user2.save()

    payload = {'email': 'user2@princeton.edu', 'organization': 'princeton'}
    response = self.client.post(
        '/registration/validateNewAdminUser/', payload)
    self.assertEqual(response.data['action_id'], '1.2.2')

  def test_case_1222(self):
    user3 = User.objects.create(
        username='user3@princeton.edu', email='user3@princeton.edu', password="Rootabega1!")
    user3.profile.organization = self.organization
    user3.is_active = False
    course = Course.objects.create(
        organization=self.organization, period="S2019", name="COS226")
    course.students.add(user3)
    course.save()
    user3.save()

    payload = {'email': 'user3@princeton.edu', 'organization': 'princeton'}
    response = self.client.post(
        '/registration/validateNewAdminUser/', payload)
    self.assertEqual(response.data['action_id'], '1.2.2')

  def test_case_2121(self):
    payload = {'email': 'newadmin@princeton.edu', 'organization': 'princeton'}
    response = self.client.post(
        '/registration/validateNewAdminUser/', payload)
    self.assertEqual(response.data['action_id'], '2.1.2')

  def test_case_2122(self):
    payload = {'email': 'newadmin@princeton.com', 'organization': 'princeton'}
    response = self.client.post(
        '/registration/validateNewAdminUser/', payload)
    self.assertEqual(response.data['action_id'], '2.1.2')

  def test_case_2221(self):
    payload = {'email': 'newadmin@acu.edu', 'organization': 'acu'}
    response = self.client.post(
        '/registration/validateNewAdminUser/', payload)
    self.assertEqual(response.data['action_id'], '2.2.2')

  def test_case_2222(self):
    payload = {'email': 'random@gmail.com', 'organization': 'acu'}
    response = self.client.post(
        '/registration/validateNewAdminUser/', payload)
    self.assertEqual(response.data['action_id'], '2.2.2')
