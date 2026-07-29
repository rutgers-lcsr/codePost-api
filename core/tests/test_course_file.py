# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests for public-capable Course Files.

Covers:
- isPublic write access (course admins only)
- publicUrl serializer output
- Unauthenticated public serving (serve_public_course_file), text and binary
- 404 for non-public / missing files
- Token rotation on unpublish (revocation)
- Archived-course edit lockdown and its unpublish-only escape hatch
- Size cap and any-type acceptance
"""
import base64

import pytest
import factory
from django.db.models.signals import post_save
from rest_framework.test import APIClient
from rest_framework import status


# A valid 1x1 transparent PNG (magic bytes satisfy File._validate_data_uri_mime).
PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAen6"
           "3NgAAAAASUVORK5CYII=")
PNG_DATA_URI = f"data:image/png;base64,{PNG_B64}"


@pytest.fixture
def course(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs314", period="f2025", organization__name="FilesOrg")


@pytest.fixture
def admin(course):
    return course.courseAdmins.first()


@pytest.fixture
def student(course):
    return course.students.first()


@pytest.fixture
def grader(course):
    return course.graders.first()


@pytest.fixture
def client():
    return APIClient()


def _create(client, course, **overrides):
    payload = {"course": course.id, "name": "notes.txt", "data": "hello", "extension": ".txt"}
    payload.update(overrides)
    return client.post("/courseFiles/", payload, format="json")


class TestPublicToggle:

    def test_admin_can_create_public_file(self, client, course, admin):
        client.force_authenticate(user=admin)
        resp = _create(client, course, isPublic=True)
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert resp.data["isPublic"] is True
        assert resp.data["publicUrl"] is not None
        assert "/courseFiles/raw/" in resp.data["publicUrl"]
        # The public URL must use the unguessable token, not the sequential id.
        assert f"/raw/{resp.data['id']}/" not in resp.data["publicUrl"]

    def test_public_url_null_when_private(self, client, course, admin):
        client.force_authenticate(user=admin)
        resp = _create(client, course, isPublic=False)
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert resp.data["isPublic"] is False
        assert resp.data["publicUrl"] is None

    def test_admin_can_toggle_public(self, client, course, admin):
        client.force_authenticate(user=admin)
        created = _create(client, course, isPublic=False)
        file_id = created.data["id"]
        resp = client.patch(f"/courseFiles/{file_id}/", {"isPublic": True}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["isPublic"] is True
        assert resp.data["publicUrl"] is not None

    def test_student_cannot_create(self, client, course, student):
        client.force_authenticate(user=student)
        resp = _create(client, course, isPublic=True)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_grader_cannot_create(self, client, course, grader):
        client.force_authenticate(user=grader)
        resp = _create(client, course, isPublic=True)
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestPublicServing:

    def test_serves_public_text_anonymously(self, client, course):
        from core.tests.factories import CourseFileFactory
        cf = CourseFileFactory(course=course, name="hi.txt", data="public text", isPublic=True)
        # No force_authenticate — anonymous request.
        resp = client.get(f"/courseFiles/raw/{cf.token}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.content == b"public text"
        assert resp["Content-Type"].startswith("text/plain")
        assert resp["X-Content-Type-Options"] == "nosniff"
        # Always download, never render inline (arbitrary content on the API origin → XSS guard).
        assert resp["Content-Disposition"].startswith("attachment")

    def test_serves_binary_datauri_with_declared_type(self, client, course):
        from core.tests.factories import CourseFileFactory
        cf = CourseFileFactory(course=course, name="pixel.png", data=PNG_DATA_URI, isPublic=True)
        resp = client.get(f"/courseFiles/raw/{cf.token}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp["Content-Type"].startswith("image/png")
        assert resp.content == base64.b64decode(PNG_B64)

    def test_404_when_not_public(self, client, course):
        from core.tests.factories import CourseFileFactory
        cf = CourseFileFactory(course=course, name="secret.txt", data="hidden", isPublic=False)
        resp = client.get(f"/courseFiles/raw/{cf.token}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_404_when_missing(self, client, db):
        import uuid
        resp = client.get(f"/courseFiles/raw/{uuid.uuid4()}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestTokenRotation:

    def test_unpublish_rotates_token_and_revokes_url(self, client, course, admin):
        client.force_authenticate(user=admin)
        created = _create(client, course, isPublic=True)
        file_id = created.data["id"]
        old_url = created.data["publicUrl"]
        assert client.get(old_url).status_code == status.HTTP_200_OK

        resp = client.patch(f"/courseFiles/{file_id}/", {"isPublic": False}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["publicUrl"] is None
        # Unpublish revokes: the shared URL dies immediately...
        assert client.get(old_url).status_code == status.HTTP_404_NOT_FOUND

        resp = client.patch(f"/courseFiles/{file_id}/", {"isPublic": True}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        new_url = resp.data["publicUrl"]
        # ...and re-publishing mints a fresh token, so the leaked URL stays dead.
        assert new_url != old_url
        assert client.get(new_url).status_code == status.HTTP_200_OK
        assert client.get(old_url).status_code == status.HTTP_404_NOT_FOUND

    def test_student_and_grader_cannot_patch_public_flag(self, client, course, student, grader):
        from core.tests.factories import CourseFileFactory
        cf = CourseFileFactory(course=course, isPublic=True)
        for user in (student, grader):
            client.force_authenticate(user=user)
            resp = client.patch(f"/courseFiles/{cf.id}/", {"isPublic": False}, format="json")
            assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_token_never_serialized(self, client, course, admin):
        client.force_authenticate(user=admin)
        created = _create(client, course, isPublic=True)
        assert "token" not in created.data
        assert "token" not in client.get(f"/courseFiles/{created.data['id']}/").data
        listed = client.get("/courseFiles/", {"course": course.id})
        assert all("token" not in item for item in listed.data)


class TestArchivedCourse:
    """Archived courses lock all edits except the unpublish-only escape hatch."""

    def _archive(self, course):
        from core.models import Course
        Course.objects.filter(pk=course.id).update(archived=True)

    def test_unpublish_only_patch_succeeds_when_archived(self, client, course, admin):
        from core.tests.factories import CourseFileFactory
        cf = CourseFileFactory(course=course, isPublic=True)
        old_token = cf.token
        self._archive(course)
        client.force_authenticate(user=admin)
        resp = client.patch(f"/courseFiles/{cf.id}/", {"isPublic": False}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        cf.refresh_from_db()
        assert cf.isPublic is False
        assert cf.token != old_token  # revocation still rotates on archived courses

    def test_other_edits_still_blocked_when_archived(self, client, course, admin):
        from core.tests.factories import CourseFileFactory
        cf = CourseFileFactory(course=course, isPublic=True)
        self._archive(course)
        client.force_authenticate(user=admin)
        for payload in ({"name": "x.txt"}, {"isPublic": True}, {"isPublic": False, "name": "x.txt"}):
            resp = client.patch(f"/courseFiles/{cf.id}/", payload, format="json")
            assert resp.status_code == status.HTTP_400_BAD_REQUEST, payload

    def test_still_serves_public_file_when_archived(self, client, course):
        from core.tests.factories import CourseFileFactory
        cf = CourseFileFactory(course=course, name="hi.txt", data="still here", isPublic=True)
        self._archive(course)
        resp = client.get(f"/courseFiles/raw/{cf.token}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.content == b"still here"


class TestStudentVisibility:
    """studentVisible gates what students see; staff always see everything."""

    def _make_files(self, course):
        from core.tests.factories import CourseFileFactory
        visible = CourseFileFactory(course=course, name="handout.txt", data="for students")
        visible.studentVisible = True
        visible.description = "Week 1 handout"
        visible.save()
        hidden = CourseFileFactory(course=course, name="answers.txt", data="staff only")
        return visible, hidden

    def test_student_list_only_visible_files(self, client, course, student):
        visible, hidden = self._make_files(course)
        client.force_authenticate(user=student)
        resp = client.get("/courseFiles/", {"course": course.id})
        assert resp.status_code == status.HTTP_200_OK
        names = {f["name"] for f in resp.data}
        assert names == {"handout.txt"}
        listed = resp.data[0]
        assert listed["description"] == "Week 1 handout"
        assert listed["data"] == "for students"

    def test_staff_list_all_files(self, client, course, admin, grader):
        self._make_files(course)
        for user in (admin, grader):
            client.force_authenticate(user=user)
            resp = client.get("/courseFiles/", {"course": course.id})
            assert resp.status_code == status.HTTP_200_OK
            assert {f["name"] for f in resp.data} == {"handout.txt", "answers.txt"}

    def test_student_retrieve_visible_ok_hidden_forbidden(self, client, course, student):
        visible, hidden = self._make_files(course)
        client.force_authenticate(user=student)
        assert client.get(f"/courseFiles/{visible.id}/").status_code == status.HTTP_200_OK
        assert client.get(f"/courseFiles/{hidden.id}/").status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_toggle_visibility(self, client, course, student):
        visible, _hidden = self._make_files(course)
        client.force_authenticate(user=student)
        resp = client.patch(f"/courseFiles/{visible.id}/", {"studentVisible": False}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_toggle_and_description_roundtrip(self, client, course, admin):
        client.force_authenticate(user=admin)
        created = _create(client, course, description="Syllabus for the term", studentVisible=True)
        assert created.status_code == status.HTTP_201_CREATED, created.data
        assert created.data["studentVisible"] is True
        assert created.data["description"] == "Syllabus for the term"
        file_id = created.data["id"]
        resp = client.patch(f"/courseFiles/{file_id}/",
                            {"studentVisible": False, "description": "updated"}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["studentVisible"] is False
        assert resp.data["description"] == "updated"

    def test_visibility_toggle_does_not_split_shared_content(self, client, course, admin):
        # studentVisible/description are per-course row fields — no copy-on-write.
        from core.tests.factories import CourseFileFactory
        cf = CourseFileFactory(course=course, name="shared.txt", data="x")
        old_content_id = cf.content_id
        client.force_authenticate(user=admin)
        resp = client.patch(f"/courseFiles/{cf.id}/",
                            {"studentVisible": True, "description": "d"}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        cf.refresh_from_db()
        assert cf.content_id == old_content_id


class TestSizeAndType:

    def test_any_type_allowed_under_cap(self, client, course, admin):
        client.force_authenticate(user=admin)
        # An unusual binary type (octet-stream skips the signature table) — allowed.
        blob = "data:application/octet-stream;base64," + base64.b64encode(b"\x00\x01\x02anything").decode()
        resp = _create(client, course, name="weird.bin", data=blob, extension=".bin", isPublic=True)
        assert resp.status_code == status.HTTP_201_CREATED, resp.data

    def test_oversize_rejected(self, client, course, admin, monkeypatch):
        import core.serializers.file as file_ser
        monkeypatch.setattr(file_ser, "MAX_COURSE_FILE_SIZE", 10)
        client.force_authenticate(user=admin)
        resp = _create(client, course, data="x" * 50)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
