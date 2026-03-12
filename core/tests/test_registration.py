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


class TestRegistrationPendingWorkflow(APITestCase):
  """Tests for the pending admin approval workflow introduced in validateNewAdminUser."""

  def setUp(self):
    self.organization = Organization.objects.create(
        name="Princeton", shortname="princeton")
    # Create an existing admin so the org is "established"
    self.admin = User.objects.create(
        username='admin@princeton.edu', email='admin@princeton.edu', password="Rootabega1!")
    self.admin.profile.organization = self.organization
    self.admin.profile.canCreateCourses = True
    self.admin.profile.canModifyRosters = True
    self.admin.is_staff = True
    self.admin.save()
    self.url = '/registration/validateNewAdminUser/'

  # ---- Existing org: new user signup returns pending=True, is_new_org=False ----

  def test_new_user_existing_org_returns_pending(self):
    """New user signing up to an existing org should be pending with is_new_org=False."""
    payload = {'email': 'newprof@princeton.edu', 'organization': 'princeton'}
    response = self.client.post(self.url, payload)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.data['success'])
    self.assertTrue(response.data['pending'])
    self.assertFalse(response.data['is_new_org'])
    self.assertEqual(response.data['action_id'], '2.1.2')

  def test_new_user_existing_org_profile_state(self):
    """New user signing up to existing org: pendingValidation=True, canModifyRosters=False, is_active=False."""
    payload = {'email': 'newprof@princeton.edu', 'organization': 'princeton'}
    self.client.post(self.url, payload)

    user = User.objects.get(email='newprof@princeton.edu')
    self.assertTrue(user.profile.pendingValidation)
    self.assertFalse(user.profile.canModifyRosters)
    self.assertFalse(user.is_active)
    self.assertEqual(user.profile.organization, self.organization)

  # ---- New org: new user signup returns pending=True, is_new_org=True ----

  def test_new_user_new_org_returns_pending(self):
    """New user creating a new org should be pending with is_new_org=True."""
    payload = {'email': 'founder@newschool.edu', 'organization': 'newschool'}
    response = self.client.post(self.url, payload)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.data['success'])
    self.assertTrue(response.data['pending'])
    self.assertTrue(response.data['is_new_org'])
    self.assertEqual(response.data['action_id'], '2.2.2')

  def test_new_user_new_org_profile_state(self):
    """New user creating a new org: pendingValidation=True, org created, is_active=False."""
    payload = {'email': 'founder@newschool.edu', 'organization': 'newschool'}
    self.client.post(self.url, payload)

    user = User.objects.get(email='founder@newschool.edu')
    self.assertTrue(user.profile.pendingValidation)
    self.assertFalse(user.profile.canModifyRosters)
    self.assertFalse(user.is_active)
    # New org should have been created
    self.assertTrue(Organization.objects.filter(shortname='newschool').exists())
    self.assertEqual(user.profile.organization.shortname, 'newschool')

  # ---- Existing user, existing org: should be pending ----

  def test_existing_user_existing_org_returns_pending(self):
    """Existing non-admin user in matching org should be pending with is_new_org=False."""
    user = User.objects.create(
        username='student@princeton.edu', email='student@princeton.edu', password="Pass1!")
    user.profile.organization = self.organization
    user.save()

    payload = {'email': 'student@princeton.edu', 'organization': 'princeton'}
    response = self.client.post(self.url, payload)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.data['pending'])
    self.assertFalse(response.data['is_new_org'])
    self.assertEqual(response.data['action_id'], '1.2.2')

  def test_existing_user_existing_org_profile_state(self):
    """Existing non-admin user gets pendingValidation=True, canModifyRosters=False."""
    user = User.objects.create(
        username='student@princeton.edu', email='student@princeton.edu', password="Pass1!")
    user.profile.organization = self.organization
    user.save()

    payload = {'email': 'student@princeton.edu', 'organization': 'princeton'}
    self.client.post(self.url, payload)

    user.refresh_from_db()
    user.profile.refresh_from_db()
    self.assertTrue(user.profile.pendingValidation)
    self.assertFalse(user.profile.canModifyRosters)

  # ---- Already an admin: should NOT be pending ----

  def test_existing_active_admin_not_pending(self):
    """An already-active admin should get pending=False."""
    admin2 = User.objects.create(
        username='admin2@princeton.edu', email='admin2@princeton.edu', password="Pass1!")
    admin2.profile.organization = self.organization
    admin2.profile.canCreateCourses = True
    admin2.profile.canModifyRosters = True
    admin2.is_active = True
    admin2.is_staff = True
    admin2.save()

    payload = {'email': 'admin2@princeton.edu', 'organization': 'princeton'}
    response = self.client.post(self.url, payload)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertFalse(response.data['pending'])
    self.assertEqual(response.data['action_id'], '1.2.1')

  # ---- Invalid form data ----

  def test_missing_email_returns_400(self):
    """Missing email should return 400."""
    payload = {'organization': 'princeton'}
    response = self.client.post(self.url, payload)
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(response.data['success'])

  def test_missing_organization_returns_400(self):
    """Missing organization should return 400."""
    payload = {'email': 'someone@test.com'}
    response = self.client.post(self.url, payload)
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(response.data['success'])
