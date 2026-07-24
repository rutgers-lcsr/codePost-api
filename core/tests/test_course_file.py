# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests for public-capable Course Files.

Covers:
- isPublic write access (course admins only)
- publicUrl serializer output
- Unauthenticated public serving (serve_public_course_file), text and binary
- 404 for non-public / missing files
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
