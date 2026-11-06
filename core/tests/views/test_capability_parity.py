# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The capabilities map drives which controls the UI shows, so it must agree with
the permission classes that enforce the same action."""
import factory
from django.db.models.signals import post_save
from rest_framework.test import APITestCase, APIClient

from core.models import RubricCategory, RubricComment
from core.tests.factories import (
    AssignmentFactory,
    CourseFactory,
    GraderFactory,
    OrganizationFactory,
    StudentFactory,
    UserFactory,
)


class TestEditRubricParity(APITestCase):

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.org = OrganizationFactory(name='parity-org')
            self.course = CourseFactory(name='parity', organization=self.org)
            self.grader = GraderFactory(course='parity', organization=self.org)
            self.course.graders.add(self.grader)
            self.assignment = AssignmentFactory(name='hw', course=self.course)

    def _set(self, course_flag, collab):
        with factory.django.mute_signals(post_save):
            self.course.allowGradersToEditRubric = course_flag
            self.course.save()
            self.assignment.collaborativeRubricMode = collab
            self.assignment.save()

    def _capability(self):
        client = APIClient()
        client.force_authenticate(user=self.grader)
        response = client.get(f'/assignments/{self.assignment.id}/capabilities/', format='json')
        self.assertEqual(response.status_code, 200)
        return response.data['capabilitiesMap']['edit_rubric']

    def _post_allowed(self):
        client = APIClient()
        client.force_authenticate(user=self.grader)
        with factory.django.mute_signals(post_save):
            response = client.post('/rubricCategories/', {
                'assignment': self.assignment.id, 'name': 'cat', 'pointLimit': 5, 'sortKey': 1,
            }, format='json')
        return response.status_code < 400

    def test_course_flag_without_collaborative_mode_matches_enforcement(self):
        self._set(course_flag=True, collab=False)
        self.assertFalse(self._post_allowed())
        self.assertFalse(self._capability())

    def test_collaborative_mode_without_course_flag_matches_enforcement(self):
        self._set(course_flag=False, collab=True)
        self.assertTrue(self._post_allowed())
        self.assertTrue(self._capability())

    def test_course_level_capability_does_not_let_flagged_grader_delete_categories(self):
        # PATCH /courses/{id}/deleteRubricCategory/ gates on the course-level capability.
        self._set(course_flag=True, collab=False)
        with factory.django.mute_signals(post_save):
            category = RubricCategory.objects.create(assignment=self.assignment, name='c', pointLimit=1, sortKey=1)
        client = APIClient()
        client.force_authenticate(user=self.grader)
        response = client.patch(f'/courses/{self.course.id}/deleteRubricCategory/', {'id': category.id}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(RubricCategory.objects.filter(id=category.id).exists())


class TestEditCourseSettingsOrgScope(APITestCase):

    def _caps(self, user, course):
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(f'/courses/{course.id}/capabilities/', format='json')
        self.assertEqual(response.status_code, 200)
        return response.data['capabilitiesMap']

    def test_org_staff_of_another_org_does_not_get_edit_course_settings(self):
        with factory.django.mute_signals(post_save):
            org_a = OrganizationFactory(name='org-a')
            org_b = OrganizationFactory(name='org-b')
            course_b = CourseFactory(name='course-b', organization=org_b)
            user = UserFactory(role='staffa', course='course-b', organization=org_b)
            course_b.students.add(user)
            user.profile.isOrgStaff = True
            user.profile.organization = org_a
            user.profile.save()
        self.assertFalse(self._caps(user, course_b)['edit_course_settings'])

    def test_org_staff_of_own_org_keeps_edit_course_settings(self):
        with factory.django.mute_signals(post_save):
            org = OrganizationFactory(name='org-own')
            course = CourseFactory(name='course-own', organization=org)
            user = UserFactory(role='staffown', course='course-own', organization=org)
            course.students.add(user)
            user.profile.isOrgStaff = True
            user.profile.organization = org
            user.profile.save()
        self.assertTrue(self._caps(user, course)['edit_course_settings'])


class TestEditUnappliedRubricCommentsParity(APITestCase):
    """edit_unapplied_rubric_comments must equal what POST/PATCH /rubricComments/ allow
    for a comment no grading Comment uses yet (non-collaborative assignment)."""

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.org = OrganizationFactory(name='unapplied-org')
            self.course = CourseFactory(name='unapplied', organization=self.org, allowGradersToEditRubric=False)
            self.admin = self.course.courseAdmins.first()
            self.grader = GraderFactory(course='unapplied', organization=self.org)
            self.course.graders.add(self.grader)
            self.editor = GraderFactory(course='unapplied', organization=self.org, count=10)
            self.course.graders.add(self.editor)
            self.course.rubricEditors.add(self.editor)
            self.student = StudentFactory(course='unapplied', organization=self.org)
            self.course.students.add(self.student)
            self.assignment = AssignmentFactory(name='hw', course=self.course, collaborativeRubricMode=False)
            self.category = RubricCategory.objects.create(
                assignment=self.assignment, name='cat', pointLimit=5, sortKey=1)
            self.unapplied = RubricComment.objects.create(category=self.category, text='free', pointDelta=1)

    def _set(self, *, flag=False, archived=False):
        with factory.django.mute_signals(post_save):
            self.course.allowGradersToEditRubric = flag
            self.course.archived = archived
            self.course.save()

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _capabilities(self, user):
        response = self._client(user).get(f'/courses/{self.course.id}/capabilities/', format='json')
        self.assertEqual(response.status_code, 200)
        return response.data['capabilitiesMap']

    def _enforced(self, user):
        client = self._client(user)
        with factory.django.mute_signals(post_save):
            added = client.post('/rubricComments/', {
                'category': self.category.id, 'text': 'new', 'pointDelta': 1}, format='json')
            patched = client.patch(f'/rubricComments/{self.unapplied.id}/', {'text': 'edited'}, format='json')
        return added.status_code < 400, patched.status_code < 400

    def _assert_parity(self, user, expected):
        self.assertEqual(self._capabilities(user).get('edit_unapplied_rubric_comments'), expected)
        self.assertEqual(self._enforced(user), (expected, expected))

    def test_admin(self):
        self._assert_parity(self.admin, True)

    def test_rubric_editor(self):
        self._assert_parity(self.editor, True)

    def test_grader_with_setting_on(self):
        self._set(flag=True)
        self._assert_parity(self.grader, True)

    def test_grader_with_setting_off(self):
        self._assert_parity(self.grader, False)

    def test_student(self):
        self._set(flag=True)
        self._assert_parity(self.student, False)

    def test_archived_course_blocks_everyone(self):
        self._set(flag=True, archived=True)
        for user in (self.admin, self.editor, self.grader):
            self._assert_parity(user, False)

    def test_edit_rubric_stays_false_for_flagged_grader(self):
        self._set(flag=True)
        self.assertFalse(self._capabilities(self.grader)['edit_rubric'])
