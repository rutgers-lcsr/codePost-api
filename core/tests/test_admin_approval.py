# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Tests for the admin approval workflow:
  - Organization-level: pending_admins, approve_admin, deny_admin
  - Dashboard-level (superuser): pending_admins, approve_pending_admin, deny_pending_admin
  - Permission checks for each endpoint
"""
from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth.models import User
from core.models import Organization, Course


class OrgPendingAdminsTestCase(APITestCase):
    """Base class with common setUp for organization approval tests."""

    def setUp(self):
        # Create organization
        self.organization = Organization.objects.create(
            name="Princeton", shortname="princeton")

        # Org staff user (can manage pending admins)
        self.org_staff = User.objects.create_user(
            username='orgstaff@princeton.edu',
            email='orgstaff@princeton.edu',
            password='TestPass1!',
        )
        self.org_staff.profile.organization = self.organization
        self.org_staff.profile.isOrgStaff = True
        self.org_staff.profile.canCreateCourses = True
        self.org_staff.profile.canModifyRosters = True
        self.org_staff.profile.save()

        # Superuser
        self.superuser = User.objects.create_superuser(
            username='super@codepost.io',
            email='super@codepost.io',
            password='SuperPass1!',
        )

        # Regular user (should NOT have access)
        self.regular_user = User.objects.create_user(
            username='regular@princeton.edu',
            email='regular@princeton.edu',
            password='TestPass1!',
        )
        self.regular_user.profile.organization = self.organization
        self.regular_user.profile.save()

        # Pending admin user
        self.pending_user = User.objects.create_user(
            username='pending@princeton.edu',
            email='pending@princeton.edu',
            password='TestPass1!',
        )
        self.pending_user.is_active = False
        self.pending_user.profile.organization = self.organization
        self.pending_user.profile.pendingValidation = True
        self.pending_user.profile.canModifyRosters = False
        self.pending_user.save()
        self.pending_user.profile.save()

        self.org_url = f'/organizations/{self.organization.pk}'


class TestOrgPendingAdminsList(OrgPendingAdminsTestCase):
    """Tests for GET /organizations/{id}/pending_admins/."""

    def test_org_staff_can_list_pending_admins(self):
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.get(f'{self.org_url}/pending_admins/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [u['email'] for u in response.data]
        self.assertIn('pending@princeton.edu', emails)

    def test_superuser_can_list_pending_admins(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(f'{self.org_url}/pending_admins/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [u['email'] for u in response.data]
        self.assertIn('pending@princeton.edu', emails)

    def test_regular_user_cannot_list_pending_admins(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(f'{self.org_url}/pending_admins/')
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_unauthenticated_cannot_list_pending_admins(self):
        response = self.client.get(f'{self.org_url}/pending_admins/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_org_staff_from_other_org_cannot_list(self):
        """Org staff from a different organization should be denied."""
        other_org = Organization.objects.create(name="Harvard", shortname="harvard")
        other_staff = User.objects.create_user(
            username='staff@harvard.edu', email='staff@harvard.edu', password='TestPass1!')
        other_staff.profile.organization = other_org
        other_staff.profile.isOrgStaff = True
        other_staff.profile.save()

        self.client.force_authenticate(user=other_staff)
        response = self.client.get(f'{self.org_url}/pending_admins/')
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_only_pending_users_returned(self):
        """Non-pending users should not appear in the list."""
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.get(f'{self.org_url}/pending_admins/')
        emails = [u['email'] for u in response.data]
        self.assertNotIn('orgstaff@princeton.edu', emails)
        self.assertNotIn('regular@princeton.edu', emails)


class TestOrgApproveAdmin(OrgPendingAdminsTestCase):
    """Tests for POST /organizations/{id}/approve_admin/."""

    def test_org_staff_can_approve_admin(self):
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(
            f'{self.org_url}/approve_admin/',
            {'user_email': 'pending@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'approved')

        # Verify user state after approval
        self.pending_user.refresh_from_db()
        self.pending_user.profile.refresh_from_db()
        self.assertTrue(self.pending_user.is_active)
        self.assertTrue(self.pending_user.profile.canCreateCourses)
        self.assertTrue(self.pending_user.profile.canModifyRosters)
        self.assertFalse(self.pending_user.profile.pendingValidation)

    def test_superuser_can_approve_admin(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            f'{self.org_url}/approve_admin/',
            {'user_email': 'pending@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'approved')

    def test_regular_user_cannot_approve_admin(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(
            f'{self.org_url}/approve_admin/',
            {'user_email': 'pending@princeton.edu'},
        )
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_approve_missing_email_returns_400(self):
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(f'{self.org_url}/approve_admin/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_nonexistent_user_returns_404(self):
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(
            f'{self.org_url}/approve_admin/',
            {'user_email': 'noone@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_approve_already_approved_user_returns_404(self):
        """Approving a user who is no longer pending should fail."""
        self.pending_user.profile.pendingValidation = False
        self.pending_user.profile.save()

        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(
            f'{self.org_url}/approve_admin/',
            {'user_email': 'pending@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestOrgDenyAdmin(OrgPendingAdminsTestCase):
    """Tests for POST /organizations/{id}/deny_admin/."""

    def test_org_staff_can_deny_admin(self):
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(
            f'{self.org_url}/deny_admin/',
            {'user_email': 'pending@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(response.data['status'], ['denied', 'denied_and_deleted'])

    def test_deny_clears_pending_validation(self):
        """Denied user should have pendingValidation=False."""
        # Give user a course membership so they aren't deleted
        course = Course.objects.create(
            organization=self.organization, period="S2019", name="COS126")
        course.students.add(self.pending_user)
        course.save()

        self.client.force_authenticate(user=self.org_staff)
        self.client.post(
            f'{self.org_url}/deny_admin/',
            {'user_email': 'pending@princeton.edu'},
        )

        self.pending_user.refresh_from_db()
        self.pending_user.profile.refresh_from_db()
        self.assertFalse(self.pending_user.profile.pendingValidation)

    def test_deny_deletes_user_with_no_courses(self):
        """User with no course memberships should be deleted on deny."""
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(
            f'{self.org_url}/deny_admin/',
            {'user_email': 'pending@princeton.edu'},
        )
        self.assertEqual(response.data['status'], 'denied_and_deleted')
        self.assertFalse(User.objects.filter(email='pending@princeton.edu').exists())

    def test_deny_keeps_user_with_course_membership(self):
        """User with course memberships should NOT be deleted on deny."""
        course = Course.objects.create(
            organization=self.organization, period="S2019", name="COS126")
        course.students.add(self.pending_user)
        course.save()

        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(
            f'{self.org_url}/deny_admin/',
            {'user_email': 'pending@princeton.edu'},
        )
        self.assertEqual(response.data['status'], 'denied')
        self.assertTrue(User.objects.filter(email='pending@princeton.edu').exists())

    def test_regular_user_cannot_deny_admin(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(
            f'{self.org_url}/deny_admin/',
            {'user_email': 'pending@princeton.edu'},
        )
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_deny_missing_email_returns_400(self):
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(f'{self.org_url}/deny_admin/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deny_nonexistent_user_returns_404(self):
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(
            f'{self.org_url}/deny_admin/',
            {'user_email': 'noone@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestDashboardPendingAdmins(APITestCase):
    """Tests for the superuser dashboard pending admin endpoints."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='super@codepost.io',
            email='super@codepost.io',
            password='SuperPass1!',
        )

        self.regular_user = User.objects.create_user(
            username='regular@test.com',
            email='regular@test.com',
            password='TestPass1!',
        )

        # Create two orgs with pending users
        self.org1 = Organization.objects.create(name="Princeton", shortname="princeton")
        self.org2 = Organization.objects.create(name="Harvard", shortname="harvard")

        self.pending1 = User.objects.create_user(
            username='pending1@princeton.edu',
            email='pending1@princeton.edu',
            password='TestPass1!',
        )
        self.pending1.is_active = False
        self.pending1.profile.organization = self.org1
        self.pending1.profile.pendingValidation = True
        self.pending1.save()
        self.pending1.profile.save()

        self.pending2 = User.objects.create_user(
            username='pending2@harvard.edu',
            email='pending2@harvard.edu',
            password='TestPass1!',
        )
        self.pending2.is_active = False
        self.pending2.profile.organization = self.org2
        self.pending2.profile.pendingValidation = True
        self.pending2.save()
        self.pending2.profile.save()

    # ---- GET /dashboard/pending_admins/ ----

    def test_superuser_can_list_all_pending_admins(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get('/dashboard/pending_admins/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [u['email'] for u in response.data]
        self.assertIn('pending1@princeton.edu', emails)
        self.assertIn('pending2@harvard.edu', emails)

    def test_regular_user_cannot_list_pending_admins(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get('/dashboard/pending_admins/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_list_pending_admins(self):
        response = self.client.get('/dashboard/pending_admins/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_pending_users_excluded(self):
        """Only users with pendingValidation=True should appear."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get('/dashboard/pending_admins/')
        emails = [u['email'] for u in response.data]
        self.assertNotIn('super@codepost.io', emails)
        self.assertNotIn('regular@test.com', emails)

    # ---- POST /dashboard/approve_pending_admin/ ----

    def test_superuser_can_approve_pending_admin(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            '/dashboard/approve_pending_admin/',
            {'user_email': 'pending1@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'approved')

        self.pending1.refresh_from_db()
        self.pending1.profile.refresh_from_db()
        self.assertTrue(self.pending1.is_active)
        self.assertTrue(self.pending1.profile.canCreateCourses)
        self.assertTrue(self.pending1.profile.canModifyRosters)
        self.assertFalse(self.pending1.profile.pendingValidation)

    def test_regular_user_cannot_approve_pending_admin(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(
            '/dashboard/approve_pending_admin/',
            {'user_email': 'pending1@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_missing_email_returns_400(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post('/dashboard/approve_pending_admin/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_nonexistent_user_returns_404(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            '/dashboard/approve_pending_admin/',
            {'user_email': 'noone@nowhere.com'},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_approve_removes_user_from_pending_list(self):
        """After approval, user should no longer appear in pending list."""
        self.client.force_authenticate(user=self.superuser)
        self.client.post(
            '/dashboard/approve_pending_admin/',
            {'user_email': 'pending1@princeton.edu'},
        )
        response = self.client.get('/dashboard/pending_admins/')
        emails = [u['email'] for u in response.data]
        self.assertNotIn('pending1@princeton.edu', emails)
        # Other pending user still there
        self.assertIn('pending2@harvard.edu', emails)

    # ---- POST /dashboard/deny_pending_admin/ ----

    def test_superuser_can_deny_pending_admin(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            '/dashboard/deny_pending_admin/',
            {'user_email': 'pending1@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(response.data['status'], ['denied', 'denied_and_deleted'])

    def test_deny_deletes_user_with_no_courses(self):
        """Denied user with no course memberships should be deleted."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            '/dashboard/deny_pending_admin/',
            {'user_email': 'pending1@princeton.edu'},
        )
        self.assertEqual(response.data['status'], 'denied_and_deleted')
        self.assertFalse(User.objects.filter(email='pending1@princeton.edu').exists())

    def test_deny_keeps_user_with_courses(self):
        """Denied user with course memberships should be kept."""
        course = Course.objects.create(
            organization=self.org1, period="S2019", name="COS126")
        course.students.add(self.pending1)
        course.save()

        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            '/dashboard/deny_pending_admin/',
            {'user_email': 'pending1@princeton.edu'},
        )
        self.assertEqual(response.data['status'], 'denied')
        self.assertTrue(User.objects.filter(email='pending1@princeton.edu').exists())
        self.pending1.profile.refresh_from_db()
        self.assertFalse(self.pending1.profile.pendingValidation)

    def test_regular_user_cannot_deny_pending_admin(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(
            '/dashboard/deny_pending_admin/',
            {'user_email': 'pending1@princeton.edu'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_deny_missing_email_returns_400(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post('/dashboard/deny_pending_admin/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deny_nonexistent_user_returns_404(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            '/dashboard/deny_pending_admin/',
            {'user_email': 'noone@nowhere.com'},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deny_removes_user_from_pending_list(self):
        """After denial, user should no longer appear in pending list."""
        self.client.force_authenticate(user=self.superuser)
        self.client.post(
            '/dashboard/deny_pending_admin/',
            {'user_email': 'pending2@harvard.edu'},
        )
        response = self.client.get('/dashboard/pending_admins/')
        emails = [u['email'] for u in response.data]
        self.assertNotIn('pending2@harvard.edu', emails)


class TestFullApprovalWorkflow(APITestCase):
    """End-to-end tests combining registration + approval."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='super@codepost.io',
            email='super@codepost.io',
            password='SuperPass1!',
        )

        # Existing org with org staff
        self.organization = Organization.objects.create(
            name="Princeton", shortname="princeton")
        self.org_staff = User.objects.create_user(
            username='orgstaff@princeton.edu',
            email='orgstaff@princeton.edu',
            password='TestPass1!',
        )
        self.org_staff.profile.organization = self.organization
        self.org_staff.profile.isOrgStaff = True
        self.org_staff.profile.canCreateCourses = True
        self.org_staff.profile.canModifyRosters = True
        self.org_staff.profile.save()

    def test_new_user_existing_org_full_approval(self):
        """Register → appears in pending list → org staff approves → user is active admin."""
        # Step 1: Register
        response = self.client.post(
            '/registration/validateNewAdminUser/',
            {'email': 'newprof@princeton.edu', 'organization': 'princeton'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['pending'])
        self.assertFalse(response.data['is_new_org'])

        # Step 2: Verify user appears in org pending list
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.get(
            f'/organizations/{self.organization.pk}/pending_admins/')
        emails = [u['email'] for u in response.data]
        self.assertIn('newprof@princeton.edu', emails)

        # Step 3: Approve
        response = self.client.post(
            f'/organizations/{self.organization.pk}/approve_admin/',
            {'user_email': 'newprof@princeton.edu'},
        )
        self.assertEqual(response.data['status'], 'approved')

        # Step 4: Verify final state
        user = User.objects.get(email='newprof@princeton.edu')
        self.assertTrue(user.is_active)
        self.assertTrue(user.profile.canCreateCourses)
        self.assertTrue(user.profile.canModifyRosters)
        self.assertFalse(user.profile.pendingValidation)

    def test_new_user_new_org_full_approval(self):
        """Register with new org → appears in dashboard pending → superuser approves."""
        # Step 1: Register
        response = self.client.post(
            '/registration/validateNewAdminUser/',
            {'email': 'founder@newschool.edu', 'organization': 'newschool'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['pending'])
        self.assertTrue(response.data['is_new_org'])

        # Step 2: Verify user appears in dashboard pending list
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get('/dashboard/pending_admins/')
        emails = [u['email'] for u in response.data]
        self.assertIn('founder@newschool.edu', emails)

        # Step 3: Approve via dashboard
        response = self.client.post(
            '/dashboard/approve_pending_admin/',
            {'user_email': 'founder@newschool.edu'},
        )
        self.assertEqual(response.data['status'], 'approved')

        # Step 4: Verify final state
        user = User.objects.get(email='founder@newschool.edu')
        self.assertTrue(user.is_active)
        self.assertTrue(user.profile.canCreateCourses)
        self.assertTrue(user.profile.canModifyRosters)
        self.assertFalse(user.profile.pendingValidation)

    def test_new_user_existing_org_full_denial(self):
        """Register → org staff denies → user is deleted (no course memberships)."""
        # Step 1: Register
        self.client.post(
            '/registration/validateNewAdminUser/',
            {'email': 'rejected@princeton.edu', 'organization': 'princeton'},
        )

        # Step 2: Deny
        self.client.force_authenticate(user=self.org_staff)
        response = self.client.post(
            f'/organizations/{self.organization.pk}/deny_admin/',
            {'user_email': 'rejected@princeton.edu'},
        )
        self.assertEqual(response.data['status'], 'denied_and_deleted')
        self.assertFalse(User.objects.filter(email='rejected@princeton.edu').exists())

    def test_new_user_new_org_full_denial(self):
        """Register with new org → superuser denies → user is deleted."""
        # Step 1: Register
        self.client.post(
            '/registration/validateNewAdminUser/',
            {'email': 'denied@newplace.edu', 'organization': 'newplace'},
        )

        # Step 2: Deny via dashboard
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            '/dashboard/deny_pending_admin/',
            {'user_email': 'denied@newplace.edu'},
        )
        self.assertEqual(response.data['status'], 'denied_and_deleted')
        self.assertFalse(User.objects.filter(email='denied@newplace.edu').exists())
