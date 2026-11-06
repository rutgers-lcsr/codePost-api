# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Org staff manage the rosters of their organization's courses.

Being org staff forces Profile.canModifyRosters on (the roster PATCH also requires
that flag), and manage_roster is granted to org staff of the course's own
organization, mirroring edit_course_settings."""
import importlib

from django.apps import apps
from rest_framework.test import APITestCase

from core.models import Profile
from core.permissions.capabilities import check_capability
from core.tests.factories import *
from core.tests.utils import request_as, setUpBase


class TestOrgStaffForcesRosterFlag(APITestCase):

    def setUp(self):
        setUpBase(self)
        self.user = UserFactory(username="dean@princeton.edu", organization=self.course.organization)

    def _promote(self, **save_kwargs):
        profile = self.user.profile
        profile.canModifyRosters = False
        profile.isOrgStaff = True
        profile.save(**save_kwargs)
        profile.refresh_from_db()
        return profile

    def test_saving_org_staff_turns_can_modify_rosters_on(self):
        self.assertTrue(self._promote().canModifyRosters)

    def test_saving_with_update_fields_still_turns_it_on(self):
        self.user.profile.save()  # existing row, so the update_fields path is taken
        self.assertTrue(self._promote(update_fields=["isOrgStaff"]).canModifyRosters)

    def test_org_staff_cannot_switch_it_off(self):
        profile = self._promote()
        profile.canModifyRosters = False
        profile.save()
        profile.refresh_from_db()
        self.assertTrue(profile.canModifyRosters)

    def test_non_org_staff_keep_their_own_setting(self):
        profile = self.user.profile
        profile.canModifyRosters = False
        profile.save()
        profile.refresh_from_db()
        self.assertFalse(profile.canModifyRosters)

    def test_migration_backfills_existing_org_staff(self):
        Profile.objects.filter(pk=self.user.profile.pk).update(isOrgStaff=True, canModifyRosters=False)
        other = UserFactory(username="prof@princeton.edu", organization=self.course.organization)
        Profile.objects.filter(pk=other.profile.pk).update(isOrgStaff=False, canModifyRosters=False)

        migration = importlib.import_module("core.migrations.0157_org_staff_can_modify_rosters")
        migration.force_roster_flag_for_org_staff(apps, None)

        self.assertTrue(Profile.objects.get(pk=self.user.profile.pk).canModifyRosters)
        self.assertFalse(Profile.objects.get(pk=other.profile.pk).canModifyRosters)


class TestOrgStaffRoster(APITestCase):

    def setUp(self):
        setUpBase(self)
        self.org_staff = self._org_staff("dean@princeton.edu", self.course.organization)
        self.url = f"/courses/{self.course.id}/roster/"

    def _org_staff(self, username, organization):
        user = UserFactory(username=username, organization=organization)
        user.profile.isOrgStaff = True
        user.profile.save()
        return user

    def test_org_staff_of_the_course_org_can_read_the_roster(self):
        response = request_as("read", self.org_staff, self.url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("students", response.data)

    def test_org_staff_of_the_course_org_can_add_a_student(self):
        students = [s.email for s in self.course.students.all()]
        response = request_as("update", self.org_staff, self.url,
                              {"students": students + ["new.student@princeton.edu"]})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(self.course.students.filter(email="new.student@princeton.edu").exists())

    def test_org_staff_of_another_org_cannot_read_or_patch_the_roster(self):
        outsider = self._org_staff("dean@harvard.edu", self.other_org_course.organization)
        self.assertEqual(request_as("read", outsider, self.url).status_code, 403)
        response = request_as("update", outsider, self.url, {"students": []})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.course.students.exists())

    def test_manage_roster_capability_follows_the_course_org(self):
        self.assertTrue(check_capability(self.org_staff, "manage_roster", self.course))
        self.assertFalse(check_capability(self.org_staff, "manage_roster", self.other_org_course))

    def test_archived_course_roster_stays_locked_for_org_staff(self):
        self.course.archived = True
        self.course.save()
        self.assertFalse(check_capability(self.org_staff, "manage_roster", self.course))
        response = request_as("update", self.org_staff, self.url, {"students": []})
        self.assertEqual(response.status_code, 403)

    def test_plain_org_member_still_cannot_patch(self):
        member = UserFactory(username="member@princeton.edu", organization=self.course.organization)
        member.profile.canModifyRosters = True
        member.profile.save()
        response = request_as("update", member, self.url, {"students": []})
        self.assertEqual(response.status_code, 403)
