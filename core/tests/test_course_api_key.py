# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests for Course-Scoped API Keys.

Covers:
- Key CRUD (create / list / update / revoke)
- CourseAPIKeyAuthentication backend
- CourseScopedJWTAuthentication backend
- Cross-course isolation (enforced by each viewset's TemplatePermission subclass:
  the service account is a courseAdmin of exactly one course, so membership
  checks fail for any other course)
- OTT → course-scoped JWT propagation
- Impersonate → course-scoped JWT propagation
"""
import pytest
from django.db.models.signals import post_save
from rest_framework.test import APIClient
from rest_framework import status

import factory

from core.models import CourseAPIKey, OneTimeToken
from core.services.course_api_key import get_or_create_course_service_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def course_a(db):
    """A course with admins and students."""
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs100", period="f2025", organization__name="TestOrg")


@pytest.fixture
def course_b(db):
    """A second course in the same org."""
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


@pytest.fixture
def plain_admin_of_a(course_a):
    """Course admin whose profile lacks the org-level canCreateCourses flag."""
    from core.tests.factories import UserFactory
    with factory.django.mute_signals(post_save):
        user = UserFactory(course=course_a.name, organization=course_a.organization, count=10)
    course_a.courseAdmins.add(user)
    return user


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def raw_key_a(course_a, admin_of_a, api_client):
    """Create a CourseAPIKey for course_a and return the raw key string."""
    api_client.force_authenticate(user=admin_of_a)
    resp = api_client.post(
        f"/courses/{course_a.id}/apiKeys/",
        {"name": "test-key"},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    # Clear forced auth so subsequent credential-based auth works
    api_client.force_authenticate(user=None)
    return resp.data["key"]


# ---------------------------------------------------------------------------
# Key CRUD
# ---------------------------------------------------------------------------

class TestCourseAPIKeyCRUD:

    def test_create_key_returns_raw_key(self, course_a, admin_of_a, api_client):
        api_client.force_authenticate(user=admin_of_a)
        resp = api_client.post(
            f"/courses/{course_a.id}/apiKeys/",
            {"name": "my-key"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.data
        assert data["key"].startswith(f"cpk_{course_a.id}_")
        assert data["name"] == "my-key"
        assert data["keyPrefix"] == f"cpk_{course_a.id}_"
        assert data["createdBy"] == admin_of_a.username

    def test_list_keys_does_not_expose_raw_key(self, course_a, admin_of_a, api_client, raw_key_a):
        api_client.force_authenticate(user=admin_of_a)
        resp = api_client.get(f"/courses/{course_a.id}/apiKeys/")
        assert resp.status_code == status.HTTP_200_OK
        keys = resp.data
        assert len(keys) >= 1
        for k in keys:
            assert "key" not in k
            assert "keyPrefix" in k

    def test_duplicate_name_rejected(self, course_a, admin_of_a, api_client, raw_key_a):
        api_client.force_authenticate(user=admin_of_a)
        resp = api_client.post(
            f"/courses/{course_a.id}/apiKeys/",
            {"name": "test-key"},  # same name as raw_key_a
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_revoke_key(self, course_a, admin_of_a, api_client, raw_key_a):
        key_obj = CourseAPIKey.objects.get(course=course_a, name="test-key")
        api_client.force_authenticate(user=admin_of_a)
        resp = api_client.delete(f"/courses/{course_a.id}/apiKeys/{key_obj.id}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not CourseAPIKey.objects.filter(pk=key_obj.pk).exists()

    def test_patch_key_name(self, course_a, admin_of_a, api_client, raw_key_a):
        key_obj = CourseAPIKey.objects.get(course=course_a, name="test-key")
        api_client.force_authenticate(user=admin_of_a)
        resp = api_client.patch(
            f"/courses/{course_a.id}/apiKeys/{key_obj.id}/",
            {"name": "renamed-key"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        key_obj.refresh_from_db()
        assert key_obj.name == "renamed-key"

    def test_deactivate_key(self, course_a, admin_of_a, api_client, raw_key_a):
        key_obj = CourseAPIKey.objects.get(course=course_a, name="test-key")
        api_client.force_authenticate(user=admin_of_a)
        resp = api_client.patch(
            f"/courses/{course_a.id}/apiKeys/{key_obj.id}/",
            {"isActive": False},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        key_obj.refresh_from_db()
        assert key_obj.is_active is False

    def test_non_admin_cannot_create_key(self, course_a, student_of_a, api_client):
        api_client.force_authenticate(user=student_of_a)
        resp = api_client.post(
            f"/courses/{course_a.id}/apiKeys/",
            {"name": "hacker-key"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_without_course_creation_flag_can_create_key(self, course_a, plain_admin_of_a, api_client):
        """Regression: minting a key must not require the org-level canCreateCourses flag."""
        assert plain_admin_of_a.profile.canCreateCourses is False
        api_client.force_authenticate(user=plain_admin_of_a)
        resp = api_client.post(
            f"/courses/{course_a.id}/apiKeys/",
            {"name": "no-flag-key"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert resp.data["key"].startswith(f"cpk_{course_a.id}_")

    def test_admin_without_course_creation_flag_can_list_keys(self, course_a, plain_admin_of_a, api_client):
        api_client.force_authenticate(user=plain_admin_of_a)
        resp = api_client.get(f"/courses/{course_a.id}/apiKeys/")
        assert resp.status_code == status.HTTP_200_OK

    def test_grader_cannot_create_or_list_keys(self, course_a, api_client):
        grader = course_a.graders.first()
        api_client.force_authenticate(user=grader)
        assert api_client.get(f"/courses/{course_a.id}/apiKeys/").status_code == status.HTTP_403_FORBIDDEN
        resp = api_client.post(
            f"/courses/{course_a.id}/apiKeys/",
            {"name": "grader-key"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_cannot_create_or_list_keys(self, course_a, admin_of_b, api_client):
        api_client.force_authenticate(user=admin_of_b)
        assert api_client.get(f"/courses/{course_a.id}/apiKeys/").status_code == status.HTTP_403_FORBIDDEN
        resp = api_client.post(
            f"/courses/{course_a.id}/apiKeys/",
            {"name": "outsider-key"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Authentication via CourseKey header
# ---------------------------------------------------------------------------

class TestCourseAPIKeyAuth:

    def test_auth_with_valid_key(self, course_a, api_client, raw_key_a):
        """Requests with a valid CourseKey header should authenticate."""
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.get(f"/courses/{course_a.id}/")
        assert resp.status_code == status.HTTP_200_OK

    def test_auth_with_invalid_key_rejected(self, course_a, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="CourseKey cpk_999_invalidhex")
        resp = api_client.get(f"/courses/{course_a.id}/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_deactivated_key_rejected(self, course_a, admin_of_a, api_client, raw_key_a):
        # Deactivate
        key_obj = CourseAPIKey.objects.get(course=course_a, name="test-key")
        key_obj.is_active = False
        key_obj.save()

        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.get(f"/courses/{course_a.id}/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Course scope enforcement
# ---------------------------------------------------------------------------

class TestCourseScopeEnforcement:

    def test_scoped_key_can_access_own_course(self, course_a, api_client, raw_key_a):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.get(f"/courses/{course_a.id}/")
        assert resp.status_code == status.HTTP_200_OK

    def test_scoped_key_cannot_access_other_course(self, course_a, course_b, api_client, raw_key_a):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.get(f"/courses/{course_b.id}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Scoped requests cannot manage keys (COURSE_SCOPED_BLOCKED_CAPABILITIES)
# ---------------------------------------------------------------------------

class TestScopedRequestCannotManageKeys:
    """A course API key (or course-scoped JWT) must not manage keys — a leaked
    key must not be able to mint or revoke credentials for its course."""

    def test_scoped_key_cannot_list_keys(self, course_a, api_client, raw_key_a):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.get(f"/courses/{course_a.id}/apiKeys/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_scoped_key_cannot_create_key(self, course_a, api_client, raw_key_a):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.post(
            f"/courses/{course_a.id}/apiKeys/",
            {"name": "escalated"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert CourseAPIKey.objects.filter(course=course_a).count() == 1

    def test_scoped_key_cannot_patch_or_delete_key(self, course_a, api_client, raw_key_a):
        key_obj = CourseAPIKey.objects.get(course=course_a, name="test-key")
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        patch = api_client.patch(
            f"/courses/{course_a.id}/apiKeys/{key_obj.id}/",
            {"isActive": False},
            format="json",
        )
        assert patch.status_code == status.HTTP_403_FORBIDDEN
        key_obj.refresh_from_db()
        assert key_obj.is_active is True
        delete = api_client.delete(f"/courses/{course_a.id}/apiKeys/{key_obj.id}/")
        assert delete.status_code == status.HTTP_403_FORBIDDEN
        assert CourseAPIKey.objects.filter(pk=key_obj.pk).exists()

    def test_scoped_jwt_cannot_manage_keys(self, course_a, admin_of_a, api_client):
        """Even a real admin's course-scoped JWT is blocked from key management."""
        from core.views.auth import access_token_for_user
        jwt_str = access_token_for_user(admin_of_a, course_id=course_a.id)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_str}")
        resp = api_client.post(
            f"/courses/{course_a.id}/apiKeys/",
            {"name": "scoped-jwt-key"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# OTT → Course-scoped JWT
# ---------------------------------------------------------------------------

class TestOTTCourseScoping:

    def test_ott_generated_via_scoped_key_stores_course(self, course_a, api_client, raw_key_a, student_of_a):
        """OTT generated while course-scoped should store the course FK."""
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.post(
            "/ott/generate/",
            {"username": student_of_a.username},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        ott = OneTimeToken.objects.get(user=student_of_a)
        assert ott.course_id == course_a.id

    def test_ott_validated_produces_scoped_jwt(self, course_a, api_client, raw_key_a, student_of_a):
        """Validating an OTT with a course should yield a JWT with course_id claim."""
        # Generate OTT via scoped key
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        gen_resp = api_client.post(
            "/ott/generate/",
            {"username": student_of_a.username},
            format="json",
        )
        assert gen_resp.status_code == status.HTTP_200_OK
        ott_token = gen_resp.data["token"]

        # Validate OTT (unauthenticated)
        client2 = APIClient()
        val_resp = client2.post(
            "/ott/validate/",
            {"token": ott_token},
            format="json",
        )
        assert val_resp.status_code == status.HTTP_200_OK
        jwt_str = val_resp.data["token"]

        # Use the JWT to access the scoped course → should work
        client2.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_str}")
        resp = client2.get(f"/courses/{course_a.id}/")
        assert resp.status_code == status.HTTP_200_OK

    def test_ott_validated_jwt_is_long_lived(self, api_client, raw_key_a, student_of_a):
        """The JWT issued from an OTT must be long-lived (≈1 year) for Jupyter sessions,
        not the SimpleJWT 5-minute default. Regression guard for the dropped never_expire."""
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta

        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        gen_resp = api_client.post(
            "/ott/generate/",
            {"username": student_of_a.username},
            format="json",
        )
        ott_token = gen_resp.data["token"]

        client2 = APIClient()
        val_resp = client2.post(
            "/ott/validate/",
            {"token": ott_token},
            format="json",
        )
        assert val_resp.status_code == status.HTTP_200_OK
        jwt_str = val_resp.data["token"]

        payload = pyjwt.decode(jwt_str, options={"verify_signature": False})
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        # Should be far in the future (much longer than the 5-min default).
        assert exp - datetime.now(timezone.utc) > timedelta(days=300)

    def test_ott_scoped_jwt_blocked_on_other_course(self, course_a, course_b, api_client, raw_key_a, student_of_a):
        """A course-scoped JWT obtained via OTT should not access another course."""
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        gen_resp = api_client.post(
            "/ott/generate/",
            {"username": student_of_a.username},
            format="json",
        )
        ott_token = gen_resp.data["token"]

        client2 = APIClient()
        val_resp = client2.post(
            "/ott/validate/",
            {"token": ott_token},
            format="json",
        )
        jwt_str = val_resp.data["token"]

        client2.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_str}")
        resp = client2.get(f"/courses/{course_b.id}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_normal_ott_has_no_course_scope(self, course_a, admin_of_a, student_of_a, api_client):
        """OTTs generated without a course key should NOT be scoped."""
        api_client.force_authenticate(user=admin_of_a)
        resp = api_client.post(
            "/ott/generate/",
            {"username": student_of_a.username},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        ott = OneTimeToken.objects.get(user=student_of_a)
        assert ott.course_id is None


# ---------------------------------------------------------------------------
# Jupyter OTT flow (end-to-end)
# ---------------------------------------------------------------------------

class TestJupyterOTTFlow:
    """End-to-end OTT flow used by Jupyter servers: a course admin mints an OTT
    for a user, the (unauthenticated) Jupyter server exchanges it for a
    long-lived JWT, then uses that JWT to act as the user."""

    def test_full_jupyter_flow(self, course_a, admin_of_a, student_of_a, api_client):
        # 1. Course admin mints an OTT for the student.
        api_client.force_authenticate(user=admin_of_a)
        gen = api_client.post(
            "/ott/generate/",
            {"username": student_of_a.username},
            format="json",
        )
        assert gen.status_code == status.HTTP_200_OK
        assert gen.data["token"]
        assert gen.data["expires_at"]
        ott_token = gen.data["token"]

        # 2. The Jupyter server (unauthenticated) exchanges the OTT for a JWT.
        jupyter = APIClient()
        val = jupyter.post(
            "/ott/validate/",
            {"token": ott_token},
            format="json",
        )
        assert val.status_code == status.HTTP_200_OK
        # The returned user data identifies the student.
        assert val.data["id"] == student_of_a.id
        assert val.data["email"] == student_of_a.email
        jwt_str = val.data["token"]

        # The JWT identifies the student, carries no course scope, and is long-lived.
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta

        payload = pyjwt.decode(jwt_str, options={"verify_signature": False})
        assert payload["user_id"] == student_of_a.id
        assert "course_id" not in payload
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp - datetime.now(timezone.utc) > timedelta(days=300)

        # 3. The Jupyter server uses the JWT to act as the student.
        jupyter.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_str}")
        resp = jupyter.get(f"/courses/{course_a.id}/")
        assert resp.status_code == status.HTTP_200_OK

    def test_ott_is_single_use(self, course_a, admin_of_a, student_of_a, api_client, monkeypatch):
        """An OTT may only be exchanged once; a replay is rejected.

        Pin DEBUG=False — the validate view deliberately allows OTT reuse in
        debug mode, so the single-use guarantee only holds in production."""
        monkeypatch.setattr("core.views.auth.DEBUG", False)
        api_client.force_authenticate(user=admin_of_a)
        gen = api_client.post(
            "/ott/generate/",
            {"username": student_of_a.username},
            format="json",
        )
        ott_token = gen.data["token"]

        jupyter = APIClient()
        first = jupyter.post("/ott/validate/", {"token": ott_token}, format="json")
        assert first.status_code == status.HTTP_200_OK

        second = jupyter.post("/ott/validate/", {"token": ott_token}, format="json")
        assert second.status_code == status.HTTP_400_BAD_REQUEST

    def test_generate_requires_permission(self, course_a, student_of_a, api_client):
        """A non-admin cannot mint an OTT for another user."""
        api_client.force_authenticate(user=student_of_a)
        other = course_a.courseAdmins.first()
        resp = api_client.post(
            "/ott/generate/",
            {"username": other.username},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_validate_invalid_token_rejected(self, db):
        """An unknown OTT is rejected."""
        jupyter = APIClient()
        resp = jupyter.post("/ott/validate/", {"token": "not-a-real-token"}, format="json")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Impersonation → Course-scoped JWT
# ---------------------------------------------------------------------------

class TestImpersonateCourseScoping:

    def test_impersonate_via_scoped_key_produces_scoped_jwt(self, course_a, api_client, raw_key_a, student_of_a):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.post(
            "/impersonate/",
            {"username": student_of_a.username},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        jwt_str = resp.data["token"]

        # Use the scoped JWT
        client2 = APIClient()
        client2.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_str}")
        # Can access scoped course
        assert client2.get(f"/courses/{course_a.id}/").status_code == status.HTTP_200_OK

    def test_impersonate_via_scoped_key_blocked_other_course(self, course_a, course_b, api_client, raw_key_a, student_of_a):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.post(
            "/impersonate/",
            {"username": student_of_a.username},
            format="json",
        )
        jwt_str = resp.data["token"]

        client2 = APIClient()
        client2.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_str}")
        assert client2.get(f"/courses/{course_b.id}/").status_code == status.HTTP_403_FORBIDDEN

    def test_impersonate_non_member_rejected_when_scoped(self, course_a, course_b, admin_of_b, api_client, raw_key_a):
        """Cannot impersonate a user who isn't in the scoped course."""
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw_key_a}")
        resp = api_client.post(
            "/impersonate/",
            {"username": admin_of_b.username},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Service user utility
# ---------------------------------------------------------------------------

class TestServiceUser:

    def test_get_or_create_is_idempotent(self, course_a):
        user1 = get_or_create_course_service_user(course_a)
        user2 = get_or_create_course_service_user(course_a)
        assert user1.pk == user2.pk
        assert user1.username == f"course-{course_a.id}-api"

    def test_service_user_is_course_admin(self, course_a):
        user = get_or_create_course_service_user(course_a)
        assert course_a.courseAdmins.filter(pk=user.pk).exists()

    def test_service_user_profile_flagged(self, course_a):
        user = get_or_create_course_service_user(course_a)
        assert user.profile.isServiceAccount is True
        assert not user.has_usable_password()
