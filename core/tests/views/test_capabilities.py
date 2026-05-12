# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
import factory
from django.db.models.signals import post_save
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from core.tests.factories import (
    CourseFactory,
    AssignmentFactory,
    GraderFactory,
    SupergraderFactory,
    UserFactory,
    OrganizationFactory,
    SubmissionFactory,
)


class TestCourseCapabilitiesEndpoint(APITestCase):
    """Tests for GET /courses/{id}/capabilities/"""

    endpoint_template = '/courses/{}/capabilities/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='testorg')
            cls.course = CourseFactory(name='cs101', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='cs101', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.student = UserFactory(role='student', course='cs101', organization=cls.org)
            cls.course.students.add(cls.student)
            cls.outsider = UserFactory(role='outsider', course='outside', organization=cls.org)

    def _get(self, user, course_id=None, params=None):
        client = APIClient()
        client.force_authenticate(user=user)
        url = self.endpoint_template.format(course_id or self.course.id)
        return client.get(url, params, format='json')

    def test_unauthenticated_returns_401(self):
        url = self.endpoint_template.format(self.course.id)
        response = APIClient().get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_member_returns_403(self):
        response = self._get(self.outsider)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_gets_full_capabilities(self):
        response = self._get(self.admin)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        caps = response.data['capabilitiesMap']
        self.assertTrue(caps['view_course'])
        self.assertTrue(caps['edit_course_settings'])
        self.assertTrue(caps['manage_roster'])
        self.assertTrue(caps['view_roster'])
        self.assertTrue(caps['manage_sections'])
        self.assertTrue(caps['view_analytics'])
        self.assertTrue(caps['create_assignment'])

    def test_grader_has_limited_capabilities(self):
        response = self._get(self.grader)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        caps = response.data['capabilitiesMap']
        self.assertTrue(caps['view_course'])
        self.assertTrue(caps['view_roster'])
        self.assertFalse(caps['edit_course_settings'])
        self.assertFalse(caps['manage_roster'])
        self.assertFalse(caps['manage_sections'])
        self.assertFalse(caps['view_analytics'])
        self.assertFalse(caps['create_assignment'])

    def test_student_has_view_only(self):
        response = self._get(self.student)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        caps = response.data['capabilitiesMap']
        self.assertTrue(caps['view_course'])
        self.assertFalse(caps['edit_course_settings'])
        self.assertFalse(caps['manage_roster'])
        self.assertFalse(caps['view_roster'])
        self.assertFalse(caps['create_assignment'])

    def test_descriptions_query_param(self):
        response = self._get(self.admin, params={'descriptions': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('capabilities', response.data)
        self.assertIn('descriptions', response.data)
        self.assertIn('view_course', response.data['descriptions'])
        self.assertTrue(len(response.data['descriptions']['view_course']) > 0)

    def test_archived_course_blocks_edits(self):
        with factory.django.mute_signals(post_save):
            self.course.archived = True
            self.course.save()
        try:
            response = self._get(self.admin)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            caps = response.data['capabilitiesMap']
            self.assertFalse(caps['edit_course_settings'])
            self.assertFalse(caps['create_assignment'])
            # view capabilities still allowed
            self.assertTrue(caps['view_course'])
            self.assertFalse(caps['manage_roster'])
            self.assertFalse(caps['manage_sections'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.archived = False
                self.course.save()


class TestAssignmentCapabilitiesEndpoint(APITestCase):
    """Tests for GET /assignments/{id}/capabilities/"""

    endpoint_template = '/assignments/{}/capabilities/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='testorg2')
            cls.course = CourseFactory(name='cs201', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='cs201', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.student = UserFactory(role='student', course='cs201', organization=cls.org)
            cls.course.students.add(cls.student)
            cls.assignment = AssignmentFactory(name='hw1', course=cls.course)

    def _get(self, user, assignment_id=None, params=None):
        client = APIClient()
        client.force_authenticate(user=user)
        url = self.endpoint_template.format(assignment_id or self.assignment.id)
        return client.get(url, params, format='json')

    def test_admin_has_all_assignment_caps(self):
        response = self._get(self.admin)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        caps = response.data['capabilitiesMap']
        self.assertTrue(caps['edit_assignment'])
        self.assertTrue(caps['copy_assignment'])
        self.assertTrue(caps['edit_rubric'])
        self.assertTrue(caps['release_grades'])
        self.assertTrue(caps['manage_test_cases'])

    def test_grader_cannot_edit_assignment(self):
        response = self._get(self.grader)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        caps = response.data['capabilitiesMap']
        self.assertFalse(caps['edit_assignment'])
        self.assertFalse(caps['copy_assignment'])
        self.assertFalse(caps['release_grades'])
        self.assertTrue(caps['view_queue'])

    def test_student_sees_visible_assignment(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.save()
        try:
            response = self._get(self.student)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            caps = response.data['capabilitiesMap']
            self.assertTrue(caps['view_assignment'])
            self.assertFalse(caps['edit_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.isVisible = False
                self.assignment.save()

    def test_student_cannot_see_hidden_assignment(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = False
            self.assignment.save()
        response = self._get(self.student)
        # Student is denied access to a hidden assignment at the permission level
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rubric_editor_can_edit_rubric(self):
        with factory.django.mute_signals(post_save):
            self.course.rubricEditors.add(self.grader)
        try:
            response = self._get(self.grader)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(response.data['capabilitiesMap']['edit_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.rubricEditors.remove(self.grader)

    def test_allow_graders_to_edit_rubric_setting(self):
        with factory.django.mute_signals(post_save):
            self.course.allowGradersToEditRubric = True
            self.course.save()
        try:
            response = self._get(self.grader)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(response.data['capabilitiesMap']['edit_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.allowGradersToEditRubric = False
                self.course.save()

    def test_descriptions_included_when_requested(self):
        response = self._get(self.admin, params={'descriptions': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('capabilities', response.data)
        self.assertIn('descriptions', response.data)
        # Assignment-level caps should be described
        self.assertIn('edit_rubric', response.data['descriptions'])


class TestSubmissionCheckPermissionCapabilities(APITestCase):
    """Tests that checkPermission now includes capabilities."""

    endpoint_template = '/submissions/{}/checkPermission/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='testorg3')
            cls.course = CourseFactory(name='cs301', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='cs301', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.student = UserFactory(role='student', course='cs301', organization=cls.org)
            cls.course.students.add(cls.student)
            cls.assignment = AssignmentFactory(name='hw1', course=cls.course)
            cls.submission = SubmissionFactory(assignment=cls.assignment)
            cls.submission.grader = cls.grader
            cls.submission.students.add(cls.student)
            cls.submission.save()

    def _get(self, user, submission_id=None):
        client = APIClient()
        client.force_authenticate(user=user)
        url = self.endpoint_template.format(submission_id or self.submission.id)
        return client.get(url, format='json')

    def test_staff_gets_capabilities_with_legacy_fields(self):
        response = self._get(self.grader)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Legacy fields still present
        self.assertTrue(response.data['read'])
        self.assertTrue(response.data['write'])
        self.assertFalse(response.data['filesOnly'])
        # New capabilities field
        self.assertIn('capabilities', response.data)
        caps = response.data['capabilities']
        self.assertTrue(caps['view_submission'])
        self.assertTrue(caps['grade_submission'])
        self.assertTrue(caps['comment_on_submission'])

    def test_student_gets_capabilities(self):
        response = self._get(self.student)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Legacy fields
        self.assertTrue(response.data['read'])
        self.assertFalse(response.data['write'])
        # Capabilities
        caps = response.data['capabilities']
        self.assertTrue(caps['view_submission'])
        self.assertFalse(caps['grade_submission'])
        self.assertFalse(caps['comment_on_submission'])


class TestCourseSerializerCapabilities(APITestCase):
    """Tests that CourseSerializer includes capabilities field."""

    endpoint_template = '/courses/{}/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='testorg4')
            cls.course = CourseFactory(name='cs401', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.student = UserFactory(role='student', course='cs401', organization=cls.org)
            cls.course.students.add(cls.student)

    def _get(self, user, course_id=None):
        client = APIClient()
        client.force_authenticate(user=user)
        url = self.endpoint_template.format(course_id or self.course.id)
        return client.get(url, format='json')

    def test_course_retrieve_includes_capabilities(self):
        response = self._get(self.admin)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('capabilities', response.data)
        caps = response.data['capabilities']
        self.assertTrue(caps['view_course'])
        self.assertTrue(caps['manage_roster'])

    def test_student_course_retrieve_has_limited_capabilities(self):
        response = self._get(self.student)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('capabilities', response.data)
        caps = response.data['capabilities']
        self.assertTrue(caps['view_course'])
        self.assertFalse(caps['manage_roster'])


# ---------------------------------------------------------------------------
# Course-level — additional role and setting coverage
# ---------------------------------------------------------------------------

class TestCourseCapsSuperGrader(APITestCase):
    """Super graders get manage_regrades and edit_rubric but not admin-only caps."""

    endpoint_template = '/courses/{}/capabilities/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='sg-org')
            cls.course = CourseFactory(name='sg-course', organization=cls.org)
            cls.super_grader = SupergraderFactory(course='sg-course', organization=cls.org)
            cls.course.superGraders.add(cls.super_grader)
            cls.course.graders.add(cls.super_grader)

    def _get(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(self.endpoint_template.format(self.course.id), format='json')

    def test_super_grader_manage_regrades(self):
        response = self._get(self.super_grader)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        caps = response.data['capabilitiesMap']
        self.assertTrue(caps['manage_regrades'])
        self.assertTrue(caps['view_course'])
        self.assertTrue(caps['view_roster'])

    def test_super_grader_cannot_edit_course_settings(self):
        response = self._get(self.super_grader)
        caps = response.data['capabilitiesMap']
        self.assertFalse(caps['edit_course_settings'])
        self.assertFalse(caps['manage_roster'])
        self.assertFalse(caps['create_assignment'])
        self.assertFalse(caps['view_analytics'])
        self.assertFalse(caps['manage_sections'])

    def test_super_grader_edit_rubric(self):
        """Super graders are graders, so edit_rubric depends on allowGradersToEditRubric or rubricEditors."""
        response = self._get(self.super_grader)
        caps = response.data['capabilitiesMap']
        # By default allowGradersToEditRubric is False and not a rubric editor
        self.assertFalse(caps['edit_rubric'])

        # Enable allowGradersToEditRubric
        with factory.django.mute_signals(post_save):
            self.course.allowGradersToEditRubric = True
            self.course.save()
        try:
            response = self._get(self.super_grader)
            self.assertTrue(response.data['capabilitiesMap']['edit_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.allowGradersToEditRubric = False
                self.course.save()


class TestCourseClaimSubmissions(APITestCase):
    """claim_submissions depends on activateQueue and role."""

    endpoint_template = '/courses/{}/capabilities/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='queue-org')
            cls.course = CourseFactory(name='queue-course', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='queue-course', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.student = UserFactory(role='student', course='queue-course', organization=cls.org)
            cls.course.students.add(cls.student)

    def _get(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(self.endpoint_template.format(self.course.id), format='json')

    def test_queue_inactive_no_claim(self):
        with factory.django.mute_signals(post_save):
            self.course.activateQueue = False
            self.course.save()
        try:
            for user in [self.admin, self.grader]:
                response = self._get(user)
                self.assertFalse(response.data['capabilitiesMap']['claim_submissions'],
                                 f"{user} should not claim when queue inactive")
        finally:
            with factory.django.mute_signals(post_save):
                self.course.activateQueue = False
                self.course.save()

    def test_queue_active_grader_can_claim(self):
        with factory.django.mute_signals(post_save):
            self.course.activateQueue = True
            self.course.save()
        try:
            response = self._get(self.grader)
            self.assertTrue(response.data['capabilitiesMap']['claim_submissions'])
            response = self._get(self.admin)
            self.assertTrue(response.data['capabilitiesMap']['claim_submissions'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.activateQueue = False
                self.course.save()

    def test_student_cannot_claim(self):
        with factory.django.mute_signals(post_save):
            self.course.activateQueue = True
            self.course.save()
        try:
            response = self._get(self.student)
            self.assertFalse(response.data['capabilitiesMap']['claim_submissions'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.activateQueue = False
                self.course.save()


class TestCourseAdminOnlyCapsExhaustive(APITestCase):
    """Verify every admin-only course cap is True for admin and False for grader/student."""

    endpoint_template = '/courses/{}/capabilities/'

    ADMIN_ONLY_CAPS = [
        'configure_ai', 'view_ai_usage', 'view_audit_log',
        'change_invite_code', 'manage_course_api_keys',
        'manage_sections', 'view_analytics',
    ]

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='admin-only-org')
            cls.course = CourseFactory(name='admin-only', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='admin-only', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.student = UserFactory(role='student', course='admin-only', organization=cls.org)
            cls.course.students.add(cls.student)

    def _get(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(self.endpoint_template.format(self.course.id), format='json')

    def test_admin_has_all_admin_only_caps(self):
        response = self._get(self.admin)
        caps = response.data['capabilitiesMap']
        for cap in self.ADMIN_ONLY_CAPS:
            self.assertTrue(caps[cap], f"Admin should have {cap}")

    def test_grader_lacks_admin_only_caps(self):
        response = self._get(self.grader)
        caps = response.data['capabilitiesMap']
        for cap in self.ADMIN_ONLY_CAPS:
            self.assertFalse(caps[cap], f"Grader should not have {cap}")

    def test_student_lacks_admin_only_caps(self):
        response = self._get(self.student)
        caps = response.data['capabilitiesMap']
        for cap in self.ADMIN_ONLY_CAPS:
            self.assertFalse(caps[cap], f"Student should not have {cap}")


class TestCourseRubricEditorCaps(APITestCase):
    """Rubric editors can edit rubric at course level."""

    endpoint_template = '/courses/{}/capabilities/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='re-org')
            cls.course = CourseFactory(name='re-course', organization=cls.org)
            cls.grader = GraderFactory(course='re-course', organization=cls.org)
            cls.course.graders.add(cls.grader)

    def _get(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(self.endpoint_template.format(self.course.id), format='json')

    def test_plain_grader_cannot_edit_rubric(self):
        response = self._get(self.grader)
        self.assertFalse(response.data['capabilitiesMap']['edit_rubric'])

    def test_rubric_editor_grader_can_edit_rubric(self):
        with factory.django.mute_signals(post_save):
            self.course.rubricEditors.add(self.grader)
        try:
            response = self._get(self.grader)
            self.assertTrue(response.data['capabilitiesMap']['edit_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.rubricEditors.remove(self.grader)

    def test_allow_graders_to_edit_rubric_setting(self):
        with factory.django.mute_signals(post_save):
            self.course.allowGradersToEditRubric = True
            self.course.save()
        try:
            response = self._get(self.grader)
            self.assertTrue(response.data['capabilitiesMap']['edit_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.allowGradersToEditRubric = False
                self.course.save()


# ---------------------------------------------------------------------------
# Assignment-level — extended coverage
# ---------------------------------------------------------------------------

class TestAssignmentCapsExtended(APITestCase):
    """Additional assignment-level capability tests."""

    endpoint_template = '/assignments/{}/capabilities/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='asgn-ext-org')
            cls.course = CourseFactory(name='asgn-ext', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='asgn-ext', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.super_grader = SupergraderFactory(course='asgn-ext', organization=cls.org)
            cls.course.superGraders.add(cls.super_grader)
            cls.course.graders.add(cls.super_grader)
            cls.student = UserFactory(role='student', course='asgn-ext', organization=cls.org)
            cls.course.students.add(cls.student)
            cls.assignment = AssignmentFactory(name='hw-ext', course=cls.course)

    def _get(self, user, assignment_id=None, params=None):
        client = APIClient()
        client.force_authenticate(user=user)
        url = self.endpoint_template.format(assignment_id or self.assignment.id)
        return client.get(url, params, format='json')

    # -- Admin-only assignment caps --
    def test_admin_manage_extensions(self):
        caps = self._get(self.admin).data['capabilitiesMap']
        self.assertTrue(caps['manage_extensions'])

    def test_grader_no_manage_extensions(self):
        caps = self._get(self.grader).data['capabilitiesMap']
        self.assertFalse(caps['manage_extensions'])

    def test_admin_view_assignment_statistics(self):
        caps = self._get(self.admin).data['capabilitiesMap']
        self.assertTrue(caps['view_assignment_statistics'])

    def test_grader_no_view_assignment_statistics(self):
        caps = self._get(self.grader).data['capabilitiesMap']
        self.assertFalse(caps['view_assignment_statistics'])

    def test_admin_manage_test_cases(self):
        caps = self._get(self.admin).data['capabilitiesMap']
        self.assertTrue(caps['manage_test_cases'])

    def test_grader_no_manage_test_cases(self):
        caps = self._get(self.grader).data['capabilitiesMap']
        self.assertFalse(caps['manage_test_cases'])

    def test_admin_manage_datasets(self):
        caps = self._get(self.admin).data['capabilitiesMap']
        self.assertTrue(caps['manage_datasets'])

    def test_grader_no_manage_datasets(self):
        caps = self._get(self.grader).data['capabilitiesMap']
        self.assertFalse(caps['manage_datasets'])

    # -- view_rubric depends on role and feedback state --
    def test_staff_always_sees_rubric(self):
        caps = self._get(self.grader).data['capabilitiesMap']
        self.assertTrue(caps['view_rubric'])

    def test_student_no_rubric_before_release(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.feedbackReleased = False
            self.assignment.liveFeedbackMode = False
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilitiesMap']
            self.assertFalse(caps['view_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.isVisible = False
                self.assignment.save()

    def test_student_sees_rubric_after_release(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.feedbackReleased = True
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilitiesMap']
            self.assertTrue(caps['view_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.feedbackReleased = False
                self.assignment.isVisible = False
                self.assignment.save()

    def test_student_sees_rubric_live_feedback(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.liveFeedbackMode = True
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilitiesMap']
            self.assertTrue(caps['view_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.liveFeedbackMode = False
                self.assignment.isVisible = False
                self.assignment.save()

    # -- download_assignment_files --
    def test_staff_can_download_files(self):
        caps = self._get(self.grader).data['capabilitiesMap']
        self.assertTrue(caps['download_assignment_files'])

    def test_student_can_download_visible_assignment_files(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilitiesMap']
            self.assertTrue(caps['download_assignment_files'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.isVisible = False
                self.assignment.save()

    # -- manage_global_templates --
    def test_admin_manage_global_templates(self):
        caps = self._get(self.admin).data['capabilitiesMap']
        self.assertTrue(caps['manage_global_templates'])

    def test_super_grader_manage_global_templates(self):
        caps = self._get(self.super_grader).data['capabilitiesMap']
        self.assertTrue(caps['manage_global_templates'])

    def test_grader_no_manage_global_templates(self):
        caps = self._get(self.grader).data['capabilitiesMap']
        self.assertFalse(caps['manage_global_templates'])

    # -- generate_ai_test_cases --
    def test_admin_generate_ai_test_cases(self):
        caps = self._get(self.admin).data['capabilitiesMap']
        self.assertTrue(caps['generate_ai_test_cases'])

    def test_super_grader_generate_ai_test_cases(self):
        caps = self._get(self.super_grader).data['capabilitiesMap']
        self.assertTrue(caps['generate_ai_test_cases'])

    def test_grader_no_generate_ai_test_cases(self):
        caps = self._get(self.grader).data['capabilitiesMap']
        self.assertFalse(caps['generate_ai_test_cases'])

    # -- upload_submission --
    def test_admin_can_upload(self):
        caps = self._get(self.admin).data['capabilitiesMap']
        self.assertTrue(caps['upload_submission'])

    def test_student_upload_when_allowed(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.allowStudentUpload = True
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilitiesMap']
            self.assertTrue(caps['upload_submission'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.allowStudentUpload = False
                self.assignment.isVisible = False
                self.assignment.save()

    def test_student_no_upload_when_disabled(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.allowStudentUpload = False
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilitiesMap']
            self.assertFalse(caps['upload_submission'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.isVisible = False
                self.assignment.save()

    # -- Archived course blocks assignment edits --
    def test_archived_course_blocks_assignment_edits(self):
        with factory.django.mute_signals(post_save):
            self.course.archived = True
            self.course.save()
        try:
            caps = self._get(self.admin).data['capabilitiesMap']
            self.assertFalse(caps['edit_assignment'])
            self.assertFalse(caps['edit_rubric'])
            self.assertFalse(caps['manage_datasets'])
            self.assertFalse(caps['upload_submission'])
            # Read-only caps still allowed
            self.assertTrue(caps['copy_assignment'])
            self.assertTrue(caps['view_queue'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.archived = False
                self.course.save()


# ---------------------------------------------------------------------------
# Submission-level — extended coverage
# ---------------------------------------------------------------------------

class TestSubmissionCapsExtended(APITestCase):
    """Extended submission capability tests via checkPermission endpoint."""

    endpoint_template = '/submissions/{}/checkPermission/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='sub-ext-org')
            cls.course = CourseFactory(name='sub-ext', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='sub-ext', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.super_grader = SupergraderFactory(course='sub-ext', organization=cls.org)
            cls.course.superGraders.add(cls.super_grader)
            cls.course.graders.add(cls.super_grader)
            cls.student = UserFactory(role='student', course='sub-ext', organization=cls.org)
            cls.course.students.add(cls.student)
            cls.assignment = AssignmentFactory(name='hw-sub', course=cls.course)
            cls.submission = SubmissionFactory(assignment=cls.assignment)
            cls.submission.grader = cls.grader
            cls.submission.students.add(cls.student)
            cls.submission.save()

    def _get(self, user, submission_id=None):
        client = APIClient()
        client.force_authenticate(user=user)
        url = self.endpoint_template.format(submission_id or self.submission.id)
        return client.get(url, format='json')

    # -- Admin capabilities --
    def test_admin_gets_full_submission_caps(self):
        response = self._get(self.admin)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        caps = response.data['capabilities']
        self.assertTrue(caps['view_submission'])
        self.assertTrue(caps['grade_submission'])
        self.assertTrue(caps['comment_on_submission'])
        self.assertTrue(caps['finalize_submission'])
        self.assertTrue(caps['unfinalize_submission'])
        self.assertTrue(caps['manage_regrades'])
        self.assertTrue(caps['view_student_identity'])
        self.assertTrue(caps['view_submission_history'])

    # -- Finalize / unfinalize --
    def test_grader_can_finalize(self):
        caps = self._get(self.grader).data['capabilities']
        self.assertTrue(caps['finalize_submission'])
        self.assertTrue(caps['unfinalize_submission'])

    def test_student_cannot_finalize(self):
        caps = self._get(self.student).data['capabilities']
        self.assertFalse(caps['finalize_submission'])
        self.assertFalse(caps['unfinalize_submission'])

    # -- view_student_identity (only admin, super_grader, section leaders) --
    def test_grader_cannot_view_student_identity_by_default(self):
        caps = self._get(self.grader).data['capabilities']
        self.assertFalse(caps['view_student_identity'])

    def test_super_grader_can_view_student_identity(self):
        # Make super_grader the grader of the submission
        with factory.django.mute_signals(post_save):
            self.submission.grader = self.super_grader
            self.submission.save()
        try:
            caps = self._get(self.super_grader).data['capabilities']
            self.assertTrue(caps['view_student_identity'])
        finally:
            with factory.django.mute_signals(post_save):
                self.submission.grader = self.grader
                self.submission.save()

    def test_section_leader_can_view_student_identity(self):
        with factory.django.mute_signals(post_save):
            section = self.course.sections.first()
            section.leaders.add(self.grader)
            section.students.add(self.student)
        try:
            caps = self._get(self.grader).data['capabilities']
            self.assertTrue(caps['view_student_identity'])
        finally:
            with factory.django.mute_signals(post_save):
                section.leaders.remove(self.grader)
                section.students.remove(self.student)

    # -- request_regrade --
    def test_student_can_request_regrade_when_allowed(self):
        with factory.django.mute_signals(post_save):
            self.assignment.allowRegradeRequests = True
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilities']
            self.assertTrue(caps['request_regrade'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.allowRegradeRequests = False
                self.assignment.save()

    def test_student_cannot_request_regrade_when_disabled(self):
        with factory.django.mute_signals(post_save):
            self.assignment.allowRegradeRequests = False
            self.assignment.save()
        caps = self._get(self.student).data['capabilities']
        self.assertFalse(caps['request_regrade'])

    def test_grader_cannot_request_regrade(self):
        with factory.django.mute_signals(post_save):
            self.assignment.allowRegradeRequests = True
            self.assignment.save()
        try:
            caps = self._get(self.grader).data['capabilities']
            self.assertFalse(caps['request_regrade'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.allowRegradeRequests = False
                self.assignment.save()

    # -- manage_regrades (admin + super_grader only) --
    def test_super_grader_manage_regrades(self):
        with factory.django.mute_signals(post_save):
            self.submission.grader = self.super_grader
            self.submission.save()
        try:
            caps = self._get(self.super_grader).data['capabilities']
            self.assertTrue(caps['manage_regrades'])
        finally:
            with factory.django.mute_signals(post_save):
                self.submission.grader = self.grader
                self.submission.save()

    def test_grader_cannot_manage_regrades(self):
        caps = self._get(self.grader).data['capabilities']
        self.assertFalse(caps['manage_regrades'])

    # -- run_autograder / run_code --
    def test_grader_can_run_code(self):
        caps = self._get(self.grader).data['capabilities']
        self.assertTrue(caps['run_autograder'])
        self.assertTrue(caps['run_code'])

    def test_student_can_run_code(self):
        caps = self._get(self.student).data['capabilities']
        self.assertFalse(caps['run_autograder'])
        self.assertTrue(caps['run_code'])

    # -- view_feedback depends on release state --
    def test_student_no_feedback_before_release(self):
        with factory.django.mute_signals(post_save):
            self.assignment.feedbackReleased = False
            self.assignment.liveFeedbackMode = False
            self.assignment.save()
        caps = self._get(self.student).data['capabilities']
        self.assertFalse(caps['view_feedback'])

    def test_student_feedback_after_release(self):
        with factory.django.mute_signals(post_save):
            self.assignment.feedbackReleased = True
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilities']
            self.assertTrue(caps['view_feedback'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.feedbackReleased = False
                self.assignment.save()

    def test_student_feedback_live_mode(self):
        with factory.django.mute_signals(post_save):
            self.assignment.liveFeedbackMode = True
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilities']
            self.assertTrue(caps['view_feedback'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.liveFeedbackMode = False
                self.assignment.save()

    def test_grader_always_sees_feedback(self):
        caps = self._get(self.grader).data['capabilities']
        self.assertTrue(caps['view_feedback'])

    # -- AI capabilities --
    def test_grader_ai_caps_when_enabled(self):
        with factory.django.mute_signals(post_save):
            self.course.ai_disabled = False
            self.course.ai_comments_disabled = False
            self.course.save()
        try:
            caps = self._get(self.grader).data['capabilities']
            self.assertTrue(caps['generate_ai_comments'])
            self.assertTrue(caps['view_ai_assistance'])
            self.assertTrue(caps['trigger_ai_assistance'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.ai_disabled = False
                self.course.save()

    def test_grader_ai_caps_when_ai_disabled(self):
        with factory.django.mute_signals(post_save):
            self.course.ai_disabled = True
            self.course.save()
        try:
            caps = self._get(self.grader).data['capabilities']
            self.assertFalse(caps['generate_ai_comments'])
            self.assertFalse(caps['view_ai_assistance'])
            self.assertFalse(caps['trigger_ai_assistance'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.ai_disabled = False
                self.course.save()

    def test_grader_ai_comments_disabled_separately(self):
        with factory.django.mute_signals(post_save):
            self.course.ai_disabled = False
            self.course.ai_comments_disabled = True
            self.course.save()
        try:
            caps = self._get(self.grader).data['capabilities']
            self.assertFalse(caps['generate_ai_comments'])
            # view/trigger AI assistance still allowed
            self.assertTrue(caps['view_ai_assistance'])
            self.assertTrue(caps['trigger_ai_assistance'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.ai_comments_disabled = False
                self.course.save()

    # -- manage_partners --
    def test_student_manage_partners_when_allowed(self):
        with factory.django.mute_signals(post_save):
            self.assignment.allowStudentUploadWithPartners = True
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilities']
            self.assertTrue(caps['manage_partners'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.allowStudentUploadWithPartners = False
                self.assignment.save()

    def test_student_no_manage_partners_when_disabled(self):
        with factory.django.mute_signals(post_save):
            self.assignment.allowStudentUploadWithPartners = False
            self.assignment.save()
        caps = self._get(self.student).data['capabilities']
        self.assertFalse(caps['manage_partners'])

    def test_grader_cannot_manage_partners(self):
        with factory.django.mute_signals(post_save):
            self.assignment.allowStudentUploadWithPartners = True
            self.assignment.save()
        try:
            caps = self._get(self.grader).data['capabilities']
            self.assertFalse(caps['manage_partners'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.allowStudentUploadWithPartners = False
                self.assignment.save()

    # -- notify_students_feedback (staff only) --
    def test_grader_can_notify_students(self):
        caps = self._get(self.grader).data['capabilities']
        self.assertTrue(caps['notify_students_feedback'])

    def test_student_cannot_notify_students(self):
        caps = self._get(self.student).data['capabilities']
        self.assertFalse(caps['notify_students_feedback'])

    # -- view_submission_history --
    def test_grader_view_submission_history(self):
        caps = self._get(self.grader).data['capabilities']
        self.assertTrue(caps['view_submission_history'])

    def test_student_no_submission_history(self):
        caps = self._get(self.student).data['capabilities']
        self.assertFalse(caps['view_submission_history'])

    # -- provide_comment_feedback --
    def test_student_can_provide_feedback(self):
        caps = self._get(self.student).data['capabilities']
        self.assertTrue(caps['provide_comment_feedback'])

    def test_grader_cannot_provide_feedback(self):
        caps = self._get(self.grader).data['capabilities']
        self.assertFalse(caps['provide_comment_feedback'])

    # -- Archived course blocks submission edits --
    def test_archived_course_blocks_submission_edits(self):
        with factory.django.mute_signals(post_save):
            self.course.archived = True
            self.course.save()
        try:
            caps = self._get(self.grader).data['capabilities']
            self.assertFalse(caps['grade_submission'])
            self.assertFalse(caps['comment_on_submission'])
            # Read-only still works
            self.assertTrue(caps['view_submission'])
            self.assertFalse(caps['finalize_submission'])
            self.assertFalse(caps['unfinalize_submission'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.archived = False
                self.course.save()

    def test_archived_blocks_manage_partners(self):
        with factory.django.mute_signals(post_save):
            self.assignment.allowStudentUploadWithPartners = True
            self.assignment.save()
            self.course.archived = True
            self.course.save()
        try:
            caps = self._get(self.student).data['capabilities']
            self.assertFalse(caps['manage_partners'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.allowStudentUploadWithPartners = False
                self.assignment.save()
                self.course.archived = False
                self.course.save()

    # -- commentFeedback setting --
    def test_comment_feedback_disabled_blocks_student(self):
        with factory.django.mute_signals(post_save):
            self.assignment.commentFeedback = False
            self.assignment.save()
        try:
            caps = self._get(self.student).data['capabilities']
            self.assertFalse(caps['provide_comment_feedback'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.commentFeedback = True
                self.assignment.save()

    # -- Students never get AI caps --
    def test_student_has_no_ai_caps(self):
        with factory.django.mute_signals(post_save):
            self.course.ai_disabled = False
            self.course.ai_comments_disabled = False
            self.course.save()
        try:
            caps = self._get(self.student).data['capabilities']
            self.assertFalse(caps['generate_ai_comments'])
            self.assertFalse(caps['view_ai_assistance'])
            self.assertFalse(caps['trigger_ai_assistance'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.ai_disabled = False
                self.course.save()


# ---------------------------------------------------------------------------
# Combined course-settings tests
# ---------------------------------------------------------------------------

class TestCourseSettingsCombinations(APITestCase):
    """Test capabilities when multiple course/assignment settings interact."""

    course_endpoint = '/courses/{}/capabilities/'
    assignment_endpoint = '/assignments/{}/capabilities/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='combo-org')
            cls.course = CourseFactory(name='combo', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='combo', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.student = UserFactory(role='student', course='combo', organization=cls.org)
            cls.course.students.add(cls.student)
            cls.assignment = AssignmentFactory(name='hw-combo', course=cls.course)
            cls.submission = SubmissionFactory(assignment=cls.assignment)
            cls.submission.grader = cls.grader
            cls.submission.students.add(cls.student)
            cls.submission.save()

    def _get_course(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(self.course_endpoint.format(self.course.id), format='json')

    def _get_assignment(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(self.assignment_endpoint.format(self.assignment.id), format='json')

    def _get_submission(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(f'/submissions/{self.submission.id}/checkPermission/', format='json')

    # -- archived + activateQueue: claim blocked even when queue active --
    def test_archived_blocks_claim_even_with_queue_active(self):
        with factory.django.mute_signals(post_save):
            self.course.activateQueue = True
            self.course.archived = True
            self.course.save()
        try:
            caps = self._get_course(self.grader).data['capabilitiesMap']
            self.assertFalse(caps['claim_submissions'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.activateQueue = False
                self.course.archived = False
                self.course.save()

    # -- archived + allowGradersToEditRubric: edit_rubric blocked --
    def test_archived_blocks_edit_rubric_even_when_allowed(self):
        with factory.django.mute_signals(post_save):
            self.course.allowGradersToEditRubric = True
            self.course.archived = True
            self.course.save()
        try:
            caps = self._get_course(self.grader).data['capabilitiesMap']
            self.assertFalse(caps['edit_rubric'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.allowGradersToEditRubric = False
                self.course.archived = False
                self.course.save()

    # -- ai_disabled does NOT affect configure_ai/view_ai_usage (admin-only, always available) --
    def test_ai_disabled_does_not_affect_admin_ai_config(self):
        with factory.django.mute_signals(post_save):
            self.course.ai_disabled = True
            self.course.save()
        try:
            caps = self._get_course(self.admin).data['capabilitiesMap']
            self.assertTrue(caps['configure_ai'])
            self.assertTrue(caps['view_ai_usage'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.ai_disabled = False
                self.course.save()

    # -- ai_disabled + ai_comments_disabled at submission level --
    def test_both_ai_flags_disabled(self):
        with factory.django.mute_signals(post_save):
            self.course.ai_disabled = True
            self.course.ai_comments_disabled = True
            self.course.save()
        try:
            caps = self._get_submission(self.grader).data['capabilities']
            self.assertFalse(caps['generate_ai_comments'])
            self.assertFalse(caps['view_ai_assistance'])
            self.assertFalse(caps['trigger_ai_assistance'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.ai_disabled = False
                self.course.ai_comments_disabled = False
                self.course.save()

    # -- archived + student upload: blocked even when allowed --
    def test_archived_blocks_student_upload(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.allowStudentUpload = True
            self.assignment.save()
            self.course.archived = True
            self.course.save()
        try:
            caps = self._get_assignment(self.student).data['capabilitiesMap']
            self.assertFalse(caps['upload_submission'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.allowStudentUpload = False
                self.assignment.isVisible = False
                self.assignment.save()
                self.course.archived = False
                self.course.save()

    # -- archived + generate_ai_test_cases: blocked --
    def test_archived_blocks_generate_ai_test_cases(self):
        with factory.django.mute_signals(post_save):
            self.course.archived = True
            self.course.save()
        try:
            caps = self._get_assignment(self.admin).data['capabilitiesMap']
            self.assertFalse(caps['generate_ai_test_cases'])
            self.assertFalse(caps['manage_datasets'])
            # copy_assignment not archived-gated
            self.assertTrue(caps['copy_assignment'])
        finally:
            with factory.django.mute_signals(post_save):
                self.course.archived = False
                self.course.save()

    # -- feedbackReleased + liveFeedbackMode both off: student can't see feedback or rubric --
    def test_no_feedback_modes_blocks_student(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.feedbackReleased = False
            self.assignment.liveFeedbackMode = False
            self.assignment.save()
        try:
            caps = self._get_assignment(self.student).data['capabilitiesMap']
            self.assertFalse(caps['view_rubric'])
            sub_caps = self._get_submission(self.student).data['capabilities']
            self.assertFalse(sub_caps['view_feedback'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.isVisible = False
                self.assignment.save()

    # -- feedbackReleased + liveFeedbackMode both on: student can see both --
    def test_both_feedback_modes_on(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.feedbackReleased = True
            self.assignment.liveFeedbackMode = True
            self.assignment.save()
        try:
            caps = self._get_assignment(self.student).data['capabilitiesMap']
            self.assertTrue(caps['view_rubric'])
            sub_caps = self._get_submission(self.student).data['capabilities']
            self.assertTrue(sub_caps['view_feedback'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.feedbackReleased = False
                self.assignment.liveFeedbackMode = False
                self.assignment.isVisible = False
                self.assignment.save()


# ---------------------------------------------------------------------------
# Response shape tests
# ---------------------------------------------------------------------------

class TestCapabilitiesResponseShape(APITestCase):
    """Verify the structure and key completeness of capability responses."""

    course_endpoint = '/courses/{}/capabilities/'
    assignment_endpoint = '/assignments/{}/capabilities/'

    COURSE_LEVEL_KEYS = {
        'view_course', 'edit_course_settings', 'manage_roster', 'view_roster',
        'manage_sections', 'view_analytics', 'configure_ai', 'view_ai_usage',
        'create_assignment', 'claim_submissions', 'edit_rubric', 'manage_regrades',
        'view_audit_log', 'change_invite_code', 'manage_course_api_keys',
    }

    ASSIGNMENT_EXTRA_KEYS = {
        'edit_assignment', 'copy_assignment', 'view_assignment', 'view_rubric',
        'release_grades', 'manage_extensions', 'view_queue', 'manage_test_cases',
        'view_assignment_statistics', 'upload_submission', 'generate_ai_test_cases',
        'manage_datasets', 'download_assignment_files', 'manage_global_templates',
    }

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='shape-org')
            cls.course = CourseFactory(name='shape-course', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.assignment = AssignmentFactory(name='hw-shape', course=cls.course)

    def _get_course(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(self.course_endpoint.format(self.course.id), format='json')

    def _get_assignment(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(self.assignment_endpoint.format(self.assignment.id), format='json')

    def test_course_response_has_capabilitiesMap_key(self):
        response = self._get_course(self.admin)
        self.assertIn('capabilitiesMap', response.data)
        self.assertIsInstance(response.data['capabilitiesMap'], dict)

    def test_course_all_keys_present(self):
        caps = self._get_course(self.admin).data['capabilitiesMap']
        missing = self.COURSE_LEVEL_KEYS - set(caps.keys())
        self.assertEqual(missing, set(), f"Missing course caps: {missing}")

    def test_course_all_values_are_booleans(self):
        caps = self._get_course(self.admin).data['capabilitiesMap']
        for key, value in caps.items():
            self.assertIsInstance(value, bool, f"{key} should be bool, got {type(value)}")

    def test_assignment_response_has_capabilitiesMap_key(self):
        response = self._get_assignment(self.admin)
        self.assertIn('capabilitiesMap', response.data)

    def test_assignment_includes_course_and_assignment_keys(self):
        caps = self._get_assignment(self.admin).data['capabilitiesMap']
        expected = self.COURSE_LEVEL_KEYS | self.ASSIGNMENT_EXTRA_KEYS
        missing = expected - set(caps.keys())
        self.assertEqual(missing, set(), f"Missing assignment caps: {missing}")

    def test_descriptions_shape(self):
        response = self._get_course(self.admin)
        # Without ?descriptions=true, no descriptions key
        self.assertNotIn('descriptions', response.data)

        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.get(
            self.course_endpoint.format(self.course.id),
            {'descriptions': 'true'}, format='json'
        )
        self.assertIn('descriptions', response.data)
        self.assertIn('capabilities', response.data)
        # Each description is a non-empty string
        for key, desc in response.data['descriptions'].items():
            self.assertIsInstance(desc, str, f"{key} description not a string")
            self.assertTrue(len(desc) > 0, f"{key} description is empty")


# ---------------------------------------------------------------------------
# check_capability / require_capability unit tests
# ---------------------------------------------------------------------------

from rest_framework.exceptions import PermissionDenied
from core.permissions.capabilities import check_capability, require_capability


class TestCheckCapabilityHelper(APITestCase):
    """Tests for the check_capability() and require_capability() functions."""

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='check-cap-org')
            cls.course = CourseFactory(name='check-cap', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='check-cap', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.student = UserFactory(role='student', course='check-cap', organization=cls.org)
            cls.course.students.add(cls.student)
            cls.assignment = AssignmentFactory(name='hw-check', course=cls.course)
            cls.submission = SubmissionFactory(assignment=cls.assignment)
            cls.submission.grader = cls.grader
            cls.submission.students.add(cls.student)
            cls.submission.save()

    # -- check_capability with Course --
    def test_check_course_admin_has_manage_roster(self):
        self.assertTrue(check_capability(self.admin, 'manage_roster', self.course))

    def test_check_course_grader_lacks_manage_roster(self):
        self.assertFalse(check_capability(self.grader, 'manage_roster', self.course))

    def test_check_course_student_has_view_course(self):
        self.assertTrue(check_capability(self.student, 'view_course', self.course))

    def test_check_course_with_enum(self):
        from core.permissions.capabilities import Capability
        self.assertTrue(check_capability(self.admin, Capability.MANAGE_ROSTER, self.course))

    # -- check_capability with Assignment --
    def test_check_assignment_admin_has_edit_assignment(self):
        self.assertTrue(check_capability(self.admin, 'edit_assignment', self.assignment))

    def test_check_assignment_grader_lacks_edit_assignment(self):
        self.assertFalse(check_capability(self.grader, 'edit_assignment', self.assignment))

    # -- check_capability with Submission --
    def test_check_submission_grader_has_grade_submission(self):
        self.assertTrue(check_capability(self.grader, 'grade_submission', self.submission))

    def test_check_submission_student_lacks_grade_submission(self):
        self.assertFalse(check_capability(self.student, 'grade_submission', self.submission))

    # -- check_capability with invalid type --
    def test_check_bad_object_type_raises_type_error(self):
        with self.assertRaises(TypeError):
            check_capability(self.admin, 'manage_roster', "not_a_model")

    # -- require_capability --
    def test_require_passes_when_allowed(self):
        # Should not raise
        require_capability(self.admin, 'manage_roster', self.course)

    def test_require_raises_permission_denied(self):
        with self.assertRaises(PermissionDenied) as ctx:
            require_capability(self.grader, 'manage_roster', self.course)
        self.assertIn('manage_roster', str(ctx.exception.detail))

    def test_require_with_enum(self):
        from core.permissions.capabilities import Capability
        with self.assertRaises(PermissionDenied):
            require_capability(self.student, Capability.EDIT_COURSE_SETTINGS, self.course)

    def test_require_assignment_level(self):
        require_capability(self.admin, 'manage_datasets', self.assignment)
        with self.assertRaises(PermissionDenied):
            require_capability(self.grader, 'manage_datasets', self.assignment)

    def test_require_submission_level(self):
        require_capability(self.grader, 'grade_submission', self.submission)
        with self.assertRaises(PermissionDenied):
            require_capability(self.student, 'grade_submission', self.submission)


class TestPlatformCapabilitiesEndpoint(APITestCase):
    """Tests for GET /capabilities/platform/"""

    url = '/capabilities/platform/'

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='platorg')

            # Regular user: no special privileges
            cls.regular_user = UserFactory(role='regular', course='plat', organization=cls.org)

            # User with canCreateCourses
            cls.course_creator = UserFactory(role='creator', course='plat', organization=cls.org)
            cls.course_creator.profile.canCreateCourses = True
            cls.course_creator.profile.save()

            # Org staff user
            cls.org_staff = UserFactory(role='orgstaff', course='plat', organization=cls.org)
            cls.org_staff.profile.isOrgStaff = True
            cls.org_staff.profile.organization = cls.org
            cls.org_staff.profile.save()

            # Superuser
            from django.contrib.auth.models import User as AuthUser
            cls.superuser = AuthUser.objects.create_superuser(
                username='super_plat@codepost.io',
                email='super_plat@codepost.io',
                password='TestPass1!',
            )

    def _get(self, user, params=None):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(self.url, params, format='json')

    # -- Auth --
    def test_unauthenticated_returns_401(self):
        response = APIClient().get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_returns_200(self):
        response = self._get(self.regular_user)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # -- Response shape --
    def test_response_has_capabilitiesMap(self):
        response = self._get(self.regular_user)
        self.assertIn('capabilitiesMap', response.data)
        caps = response.data['capabilitiesMap']
        self.assertIn('create_course', caps)
        self.assertIn('manage_organization', caps)
        self.assertIn('impersonate_user', caps)
        self.assertIn('access_admin_dashboard', caps)

    def test_descriptions_flag_works(self):
        response = self._get(self.regular_user, {'descriptions': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('capabilities', response.data)
        self.assertIn('descriptions', response.data)
        descs = response.data['descriptions']
        self.assertIn('create_course', descs)
        self.assertIsInstance(descs['create_course'], str)
        self.assertTrue(len(descs['create_course']) > 0)

    # -- Regular user (no privileges) --
    def test_regular_user_has_no_capabilities(self):
        caps = self._get(self.regular_user).data['capabilitiesMap']
        self.assertFalse(caps['create_course'])
        self.assertFalse(caps['manage_organization'])
        self.assertFalse(caps['impersonate_user'])
        self.assertFalse(caps['access_admin_dashboard'])

    # -- Course creator --
    def test_course_creator_can_create_course(self):
        caps = self._get(self.course_creator).data['capabilitiesMap']
        self.assertTrue(caps['create_course'])

    def test_course_creator_cannot_manage_org(self):
        caps = self._get(self.course_creator).data['capabilitiesMap']
        self.assertFalse(caps['manage_organization'])

    def test_course_creator_cannot_impersonate(self):
        caps = self._get(self.course_creator).data['capabilitiesMap']
        self.assertFalse(caps['impersonate_user'])

    # -- Org staff --
    def test_org_staff_can_manage_organization(self):
        caps = self._get(self.org_staff).data['capabilitiesMap']
        self.assertTrue(caps['manage_organization'])

    def test_org_staff_cannot_impersonate(self):
        caps = self._get(self.org_staff).data['capabilitiesMap']
        self.assertFalse(caps['impersonate_user'])

    def test_org_staff_cannot_access_admin_dashboard(self):
        caps = self._get(self.org_staff).data['capabilitiesMap']
        self.assertFalse(caps['access_admin_dashboard'])

    # -- Superuser --
    def test_superuser_has_all_capabilities(self):
        caps = self._get(self.superuser).data['capabilitiesMap']
        self.assertTrue(caps['create_course'])
        self.assertTrue(caps['manage_organization'])
        self.assertTrue(caps['impersonate_user'])
        self.assertTrue(caps['access_admin_dashboard'])


# ---------------------------------------------------------------------------
# Enforcement tests — verify migrated views reject unauthorized users
# ---------------------------------------------------------------------------

class TestCapabilityEnforcementOnViews(APITestCase):
    """
    Tests that views using require_capability correctly return 403
    for users who lack the necessary capability.
    """

    @classmethod
    def setUpTestData(cls):
        with factory.django.mute_signals(post_save):
            cls.org = OrganizationFactory(name='enforcement-org')
            cls.course = CourseFactory(name='enforcement', organization=cls.org)
            cls.admin = cls.course.courseAdmins.first()
            cls.grader = GraderFactory(course='enforcement', organization=cls.org)
            cls.course.graders.add(cls.grader)
            cls.student = UserFactory(role='student', course='enforcement', organization=cls.org)
            cls.course.students.add(cls.student)
            cls.outsider = UserFactory(role='outsider', course='outside', organization=cls.org)
            cls.assignment = AssignmentFactory(name='hw-enf', course=cls.course)
            cls.submission = SubmissionFactory(assignment=cls.assignment)
            cls.submission.grader = cls.grader
            cls.submission.students.add(cls.student)
            cls.submission.save()

    def _client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    # -- queueLength: requires view_queue (course staff only) --
    def test_queueLength_student_forbidden(self):
        url = f'/assignments/{self.assignment.id}/queueLength/'
        resp = self._client_for(self.student).get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_queueLength_outsider_forbidden(self):
        url = f'/assignments/{self.assignment.id}/queueLength/'
        resp = self._client_for(self.outsider).get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_queueLength_grader_allowed(self):
        url = f'/assignments/{self.assignment.id}/queueLength/'
        resp = self._client_for(self.grader).get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_queueLength_admin_allowed(self):
        url = f'/assignments/{self.assignment.id}/queueLength/'
        resp = self._client_for(self.admin).get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # -- download: requires download_assignment_files (course member) --
    def test_download_outsider_forbidden(self):
        url = f'/assignments/{self.assignment.id}/download/'
        resp = self._client_for(self.outsider).get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_download_student_allowed(self):
        with factory.django.mute_signals(post_save):
            self.assignment.isVisible = True
            self.assignment.save()
        try:
            url = f'/assignments/{self.assignment.id}/download/'
            resp = self._client_for(self.student).get(url)
            # 200 or 204 (no files) — either means access was granted
            self.assertIn(resp.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.isVisible = False
                self.assignment.save()

    def test_download_grader_allowed(self):
        url = f'/assignments/{self.assignment.id}/download/'
        resp = self._client_for(self.grader).get(url)
        self.assertIn(resp.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    # -- testResults: requires view_submission --
    def test_testResults_outsider_forbidden(self):
        url = f'/submissions/{self.submission.id}/testResults/'
        resp = self._client_for(self.outsider).get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_testResults_grader_allowed(self):
        url = f'/submissions/{self.submission.id}/testResults/'
        resp = self._client_for(self.grader).get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_testResults_student_allowed(self):
        url = f'/submissions/{self.submission.id}/testResults/'
        resp = self._client_for(self.student).get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # -- checkPermission: outsider gets read=false --
    def test_checkPermission_outsider_read_false(self):
        url = f'/submissions/{self.submission.id}/checkPermission/'
        resp = self._client_for(self.outsider).get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['read'])
        self.assertFalse(resp.data['write'])
        self.assertFalse(resp.data['filesOnly'])

    def test_checkPermission_grader_has_write(self):
        url = f'/submissions/{self.submission.id}/checkPermission/'
        resp = self._client_for(self.grader).get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['read'])
        self.assertTrue(resp.data['write'])
        self.assertFalse(resp.data['filesOnly'])

    def test_checkPermission_student_read_only(self):
        url = f'/submissions/{self.submission.id}/checkPermission/'
        resp = self._client_for(self.student).get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['read'])
        self.assertFalse(resp.data['write'])

    def test_checkPermission_student_filesOnly_when_no_feedback(self):
        with factory.django.mute_signals(post_save):
            self.assignment.feedbackReleased = False
            self.assignment.liveFeedbackMode = False
            self.assignment.save()
        url = f'/submissions/{self.submission.id}/checkPermission/'
        resp = self._client_for(self.student).get(url)
        self.assertTrue(resp.data['filesOnly'])

    def test_checkPermission_student_full_when_feedback_released(self):
        with factory.django.mute_signals(post_save):
            self.assignment.feedbackReleased = True
            self.assignment.save()
        try:
            url = f'/submissions/{self.submission.id}/checkPermission/'
            resp = self._client_for(self.student).get(url)
            self.assertFalse(resp.data['filesOnly'])
        finally:
            with factory.django.mute_signals(post_save):
                self.assignment.feedbackReleased = False
                self.assignment.save()

    # -- email: requires manage_roster (admin only) --
    def test_email_student_forbidden(self):
        url = f'/users/{self.student.email}/email/'
        resp = self._client_for(self.student).post(url, {
            'course': self.course.id,
            'template': 'generic',
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_email_grader_forbidden(self):
        url = f'/users/{self.student.email}/email/'
        resp = self._client_for(self.grader).post(url, {
            'course': self.course.id,
            'template': 'generic',
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
