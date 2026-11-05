# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.test import APITestCase

from core.tests.factories import OrganizationFactory, UserFactory


class UserUpdateTests(APITestCase):
  def setUp(self):
    org = OrganizationFactory()
    self.staff = UserFactory(username='staff@example.com', email='staff@example.com', organization=org, is_superuser=True, is_staff=True)
    self.user = UserFactory(username='one@example.com', email='one@example.com', organization=org)
    self.client.force_authenticate(user=self.staff)

  def test_patch_is_org_staff_persists(self):
    # The profile flag rides along in the same PATCH as the user's own fields.
    res = self.client.patch(f'/users/{self.user.email}/', {'isOrgStaff': True, 'canCreateCourses': True}, format='json')
    self.assertEqual(res.status_code, 200, res.data)
    self.user.refresh_from_db()
    self.assertTrue(self.user.profile.isOrgStaff)
    self.assertTrue(self.user.profile.canCreateCourses)
    self.assertTrue(res.data['isOrgStaff'])

    res = self.client.patch(f'/users/{self.user.email}/', {'isOrgStaff': False}, format='json')
    self.assertEqual(res.status_code, 200, res.data)
    self.user.refresh_from_db()
    self.assertFalse(self.user.profile.isOrgStaff)
