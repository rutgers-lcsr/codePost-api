# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Privilege-escalation regression tests for /impersonate/ and /ott/generate/.

Both endpoints hand out a credential carrying everything the target can do in
every course (the ``course_id`` claim on a scoped JWT is not an isolation
boundary), so neither may yield a user more privileged than the requester.
"""
import factory
import pytest
from django.db.models.signals import post_save
from rest_framework import status
from rest_framework.test import APIClient

from core.models import CourseAPIKey, OneTimeToken, User


@pytest.fixture
def course_a(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs100", period="f2025", organization__name="TestOrg")


@pytest.fixture
def course_b(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs200", period="f2025", organization__name="TestOrg")


@pytest.fixture
def admin_of_a(course_a):
    return course_a.courseAdmins.first()


@pytest.fixture
def student_of_a(course_a):
    return course_a.students.first()


@pytest.fixture
def admin_of_b(course_b):
    return course_b.courseAdmins.first()


def _key_client(course, created_by, scope):
    raw_key = CourseAPIKey.generate_key(course.id)
    CourseAPIKey.objects.create(
        course=course, name=f"{scope}-key", created_by=created_by, scope=scope,
        key_prefix=raw_key.rsplit("_", 1)[0] + "_", hashed_key=CourseAPIKey.hash_key(raw_key),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key}")
    return client


@pytest.fixture
def key_client(course_a, admin_of_a):
    """A client authenticated with a read-scope (the default) course_a API key."""
    return _key_client(course_a, admin_of_a, "read")


@pytest.fixture
def admin_key_client(course_a, admin_of_a):
    """A client authenticated with an admin-scope course_a API key, as JupyterHub uses."""
    return _key_client(course_a, admin_of_a, "admin")


def _as(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _bearer(token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _impersonate(client, user):
    return client.post("/impersonate/", {"username": user.username}, format="json")


def _generate_ott(client, user):
    return client.post("/ott/generate/", {"username": user.username}, format="json")


def _superuser(username, **kwargs):
    return User.objects.create_user(username, f"{username}@x.com", "pw", is_superuser=True, is_staff=True, **kwargs)


class TestImpersonateAllowed:

    def test_course_admin_can_impersonate_student(self, admin_of_a, student_of_a):
        resp = _impersonate(_as(admin_of_a), student_of_a)
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["id"] == student_of_a.id

    def test_course_admin_can_impersonate_grader(self, course_a, admin_of_a):
        assert _impersonate(_as(admin_of_a), course_a.graders.first()).status_code == status.HTTP_200_OK

    def test_course_key_can_impersonate_student(self, key_client, student_of_a):
        assert _impersonate(key_client, student_of_a).status_code == status.HTTP_200_OK

    def test_admin_key_can_impersonate_instructor(self, admin_key_client, admin_of_a):
        resp = _impersonate(admin_key_client, admin_of_a)
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["id"] == admin_of_a.id

    def test_admin_key_can_impersonate_instructor_who_also_teaches_elsewhere(self, course_b, admin_of_a, admin_key_client):
        course_b.courseAdmins.add(admin_of_a)
        assert _impersonate(admin_key_client, admin_of_a).status_code == status.HTTP_200_OK

    def test_admin_key_can_impersonate_org_staff_instructor(self, admin_of_a, admin_key_client):
        # Instructors are trusted with admin keys, so org staff in the course are reachable.
        admin_of_a.profile.isOrgStaff = True
        admin_of_a.profile.save()
        assert _impersonate(admin_key_client, admin_of_a).status_code == status.HTTP_200_OK
        assert _generate_ott(admin_key_client, admin_of_a).status_code == status.HTTP_200_OK

    def test_admin_key_can_impersonate_grader_who_teaches_elsewhere(self, course_a, admin_of_b, admin_key_client):
        course_a.graders.add(admin_of_b)
        assert _impersonate(admin_key_client, admin_of_b).status_code == status.HTTP_200_OK

    def test_superuser_can_impersonate_anyone(self, admin_of_a):
        assert _impersonate(_as(_superuser("root")), admin_of_a).status_code == status.HTTP_200_OK

    def test_staff_can_impersonate_course_admin(self, admin_of_a):
        staff = User.objects.create_user("stf", "stf@x.com", "pw", is_staff=True)
        assert _impersonate(_as(staff), admin_of_a).status_code == status.HTTP_200_OK


class TestImpersonateEscalationBlocked:

    def test_course_key_cannot_impersonate_admin_of_other_course(self, course_a, admin_of_b, key_client):
        course_a.graders.add(admin_of_b)
        assert _impersonate(key_client, admin_of_b).status_code == status.HTTP_403_FORBIDDEN

    def test_read_and_write_keys_cannot_impersonate_instructor(self, course_a, admin_of_a, key_client):
        assert _impersonate(key_client, admin_of_a).status_code == status.HTTP_403_FORBIDDEN
        write_key = _key_client(course_a, admin_of_a, "write")
        assert _impersonate(write_key, admin_of_a).status_code == status.HTTP_403_FORBIDDEN

    def test_admin_key_cannot_impersonate_superuser_instructor(self, course_a, admin_key_client):
        su = _superuser("root")
        course_a.courseAdmins.add(su)
        assert _impersonate(admin_key_client, su).status_code == status.HTTP_403_FORBIDDEN

    def test_read_key_cannot_impersonate_org_staff_student(self, student_of_a, key_client):
        student_of_a.profile.isOrgStaff = True
        student_of_a.profile.save()
        assert _impersonate(key_client, student_of_a).status_code == status.HTTP_403_FORBIDDEN

    def test_admin_key_cannot_impersonate_member_of_other_course_only(self, admin_of_b, admin_key_client):
        assert _impersonate(admin_key_client, admin_of_b).status_code == status.HTTP_403_FORBIDDEN

    def test_instructor_token_from_key_cannot_impersonate_co_instructor(self, course_a, admin_of_a, admin_key_client):
        # Only the key itself may become an instructor, not a scoped JWT it was handed.
        resp = _impersonate(admin_key_client, admin_of_a)
        assert resp.status_code == status.HTTP_200_OK
        instructor = _bearer(resp.data["token"])
        assert _impersonate(instructor, course_a.courseAdmins.exclude(pk=admin_of_a.pk).first()).status_code == status.HTTP_403_FORBIDDEN

    def test_student_with_scoped_jwt_cannot_impersonate(self, course_a, student_of_a, admin_of_a):
        # A student obtains a course-scoped JWT legitimately (e.g. the SEB quiz launch OTT).
        ott = OneTimeToken.objects.create(user=student_of_a, course=course_a)
        resp = APIClient().post("/ott/exchange/", {"token": str(ott.token)}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        student = _bearer(resp.data["token"])
        assert _impersonate(student, admin_of_a).status_code == status.HTTP_403_FORBIDDEN
        assert _impersonate(student, course_a.students.last()).status_code == status.HTTP_403_FORBIDDEN

    def test_course_admin_cannot_impersonate_enrolled_superuser(self, course_a, admin_of_a):
        su = _superuser("root")
        course_a.students.add(su)
        assert _impersonate(_as(admin_of_a), su).status_code == status.HTTP_403_FORBIDDEN

    def test_course_admin_cannot_impersonate_enrolled_staff(self, course_a, admin_of_a):
        staff = User.objects.create_user("stf", "stf@x.com", "pw", is_staff=True)
        course_a.graders.add(staff)
        assert _impersonate(_as(admin_of_a), staff).status_code == status.HTTP_403_FORBIDDEN

    def test_course_admin_cannot_impersonate_org_staff(self, course_a, admin_of_a, student_of_a):
        student_of_a.profile.isOrgStaff = True
        student_of_a.profile.save()
        assert _impersonate(_as(admin_of_a), student_of_a).status_code == status.HTTP_403_FORBIDDEN

    def test_course_admin_cannot_impersonate_admin_of_other_course(self, course_a, admin_of_a, admin_of_b):
        course_a.graders.add(admin_of_b)
        assert _impersonate(_as(admin_of_a), admin_of_b).status_code == status.HTTP_403_FORBIDDEN

    def test_course_admin_cannot_impersonate_co_admin(self, course_a, admin_of_a):
        assert _impersonate(_as(admin_of_a), course_a.courseAdmins.last()).status_code == status.HTTP_403_FORBIDDEN

    def test_staff_cannot_impersonate_superuser(self, db):
        staff = User.objects.create_user("stf", "stf@x.com", "pw", is_staff=True)
        assert _impersonate(_as(staff), _superuser("root")).status_code == status.HTTP_403_FORBIDDEN

    def test_never_expire_string_false_is_not_long_lived(self, admin_of_a):
        resp = _as(_superuser("root")).post(
            "/impersonate/", {"username": admin_of_a.username, "never_expire": "false"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert "refresh" in resp.data


class TestGenerateOttEscalationBlocked:

    def test_course_admin_can_generate_for_student_and_co_admin(self, course_a, admin_of_a, student_of_a):
        client = _as(admin_of_a)
        assert _generate_ott(client, student_of_a).status_code == status.HTTP_200_OK
        assert _generate_ott(client, course_a.courseAdmins.last()).status_code == status.HTTP_200_OK

    def test_course_key_can_generate_for_student(self, key_client, student_of_a):
        assert _generate_ott(key_client, student_of_a).status_code == status.HTTP_200_OK

    def test_admin_key_can_generate_for_instructor_who_also_teaches_elsewhere(self, course_b, admin_of_a, admin_key_client):
        # The JupyterHub launch path: admin-scope key mints an OTT for whoever opens the server.
        course_b.courseAdmins.add(admin_of_a)
        assert _generate_ott(admin_key_client, admin_of_a).status_code == status.HTTP_200_OK

    def test_read_key_cannot_generate_for_instructor(self, admin_of_a, key_client):
        assert _generate_ott(key_client, admin_of_a).status_code == status.HTTP_403_FORBIDDEN

    def test_read_key_cannot_generate_for_student_who_teaches_elsewhere(self, course_b, student_of_a, key_client):
        course_b.courseAdmins.add(student_of_a)
        assert _generate_ott(key_client, student_of_a).status_code == status.HTTP_403_FORBIDDEN

    def test_admin_key_cannot_generate_for_superuser_instructor(self, course_a, admin_key_client):
        su = _superuser("root")
        course_a.courseAdmins.add(su)
        assert _generate_ott(admin_key_client, su).status_code == status.HTTP_403_FORBIDDEN

    def test_student_with_scoped_jwt_cannot_generate_for_instructor(self, course_a, student_of_a, admin_of_a):
        ott = OneTimeToken.objects.create(user=student_of_a, course=course_a)
        resp = APIClient().post("/ott/exchange/", {"token": str(ott.token)}, format="json")
        assert _generate_ott(_bearer(resp.data["token"]), admin_of_a).status_code == status.HTTP_403_FORBIDDEN

    def test_course_admin_cannot_generate_for_co_admin_superuser(self, course_a, admin_of_a):
        su = _superuser("root")
        course_a.courseAdmins.add(su)
        assert _generate_ott(_as(admin_of_a), su).status_code == status.HTTP_403_FORBIDDEN

    def test_course_admin_cannot_generate_for_admin_of_other_course(self, course_a, admin_of_a, admin_of_b):
        course_a.courseAdmins.add(admin_of_b)
        assert _generate_ott(_as(admin_of_a), admin_of_b).status_code == status.HTTP_403_FORBIDDEN

    def test_staff_cannot_generate_outside_their_courses(self, admin_of_a):
        # Staff impersonate via /impersonate/ (refreshable tokens), not 365-day OTT tokens.
        staff = User.objects.create_user("stf", "stf@x.com", "pw", is_staff=True)
        assert _generate_ott(_as(staff), admin_of_a).status_code == status.HTTP_403_FORBIDDEN


class TestSuperuserCreatedAdminKey:
    """A superuser can already become anyone, so an admin-scope key a superuser
    created may log in superuser/staff members of its course (JupyterHub logins
    for site admins). Instructor-created keys stay blocked — see
    test_admin_key_cannot_generate_for_superuser_instructor."""

    def test_generates_ott_for_superuser_member(self, course_a):
        su = _superuser("root")
        course_a.courseAdmins.add(su)
        client = _key_client(course_a, su, "admin")
        assert _generate_ott(client, su).status_code == status.HTTP_200_OK

    def test_generates_ott_and_impersonates_other_superuser_member(self, course_a):
        creator, other = _superuser("root"), _superuser("root2")
        course_a.students.add(other)
        client = _key_client(course_a, creator, "admin")
        assert _generate_ott(client, other).status_code == status.HTTP_200_OK
        assert _impersonate(client, other).status_code == status.HTTP_200_OK

    def test_generates_ott_for_staff_member(self, course_a):
        staff = User.objects.create_user("stf", "stf@x.com", "pw", is_staff=True)
        course_a.graders.add(staff)
        client = _key_client(course_a, _superuser("root"), "admin")
        assert _generate_ott(client, staff).status_code == status.HTTP_200_OK

    def test_read_and_write_keys_still_blocked(self, course_a):
        su = _superuser("root")
        course_a.courseAdmins.add(su)
        for scope in ("read", "write"):
            client = _key_client(course_a, su, scope)
            assert _generate_ott(client, su).status_code == status.HTTP_403_FORBIDDEN, scope

    def test_superuser_must_still_be_a_course_member(self, course_a):
        su = _superuser("root")
        client = _key_client(course_a, su, "admin")
        assert _generate_ott(client, _superuser("root2")).status_code == status.HTTP_403_FORBIDDEN

    def test_demoted_creator_revokes_the_exception(self, course_a):
        creator, target = _superuser("root"), _superuser("root2")
        course_a.courseAdmins.add(target)
        client = _key_client(course_a, creator, "admin")
        creator.is_superuser = False
        creator.save()
        assert _generate_ott(client, target).status_code == status.HTTP_403_FORBIDDEN

    def test_scoped_jwt_from_key_cannot_reach_superusers(self, course_a, admin_of_a):
        # The exception belongs to the key itself, not to tokens it hands out.
        su = _superuser("root")
        course_a.courseAdmins.add(su)
        client = _key_client(course_a, su, "admin")
        resp = _impersonate(client, admin_of_a)
        assert resp.status_code == status.HTTP_200_OK
        assert _generate_ott(_bearer(resp.data["token"]), su).status_code == status.HTTP_403_FORBIDDEN
