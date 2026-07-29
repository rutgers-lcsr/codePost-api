# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Copy-on-write CourseFile sharing across course clones.

Cloning links the destination CourseFile row to the SAME CourseFileContent (same data,
same token, same public state) so public URLs embedded in cloned markdown keep working.
A physical copy only happens when a sharing course diverges (edits data or toggles
isPublic): the acting course detaches onto a fresh content, and the other courses keep
the original content and token — their URLs never break.
"""
import factory
import pytest
from django.db.models.signals import post_save
from rest_framework import status
from rest_framework.test import APIClient

from core.models import CourseFile, CourseFileContent
from core.services.quiz_cloning import clone_course_files


@pytest.fixture
def source(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs510src", period="f2026", organization__name="ShareOrg")


@pytest.fixture
def dest(source):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs510dst", period="s2027", organization=source.organization)


@pytest.fixture
def source_admin(source):
    return source.courseAdmins.first()


@pytest.fixture
def dest_admin(dest):
    return dest.courseAdmins.first()


@pytest.fixture
def client():
    return APIClient()


def _shared_file(source, dest, *, public=True, name="handout.txt", data="shared text"):
    """A file in source shared (via clone) into dest. Returns (src_row, cloned_row)."""
    from core.tests.factories import CourseFileFactory
    src = CourseFileFactory(course=source, name=name, data=data, isPublic=public)
    clone_course_files(source, dest, names={name})
    return src, dest.files.get(name=name)


def _raw_url(token):
    return f"/courseFiles/raw/{token}/"


class TestCloneSharing:

    def test_clone_shares_content_and_url_stays_live(self, client, source, dest):
        src, cloned = _shared_file(source, dest)
        assert cloned.content_id == src.content_id
        assert cloned.token == src.token
        assert cloned.isPublic is True
        resp = client.get(_raw_url(src.token))  # anonymous
        assert resp.status_code == status.HTTP_200_OK
        assert resp.content == b"shared text"

    def test_clone_creates_no_new_content_rows(self, source, dest):
        from core.tests.factories import CourseFileFactory
        CourseFileFactory(course=source, name="a.txt", data="A")
        CourseFileFactory(course=source, name="b.txt", data="B")
        before = CourseFileContent.objects.count()
        created = clone_course_files(source, dest)
        assert created == 2
        assert CourseFileContent.objects.count() == before

    def test_private_file_shares_and_stays_private(self, client, source, dest):
        src, cloned = _shared_file(source, dest, public=False)
        assert cloned.content_id == src.content_id
        assert cloned.isPublic is False
        assert client.get(_raw_url(src.token)).status_code == status.HTTP_404_NOT_FOUND


class TestCopyOnWrite:

    def test_unpublish_by_clone_splits_and_source_url_stays_live(
            self, client, source, dest, dest_admin):
        src, cloned = _shared_file(source, dest)
        old_token = src.token

        client.force_authenticate(user=dest_admin)
        resp = client.patch(f"/courseFiles/{cloned.id}/", {"isPublic": False}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["publicUrl"] is None

        cloned.refresh_from_db()
        src.refresh_from_db()
        assert cloned.content_id != src.content_id  # the acting row detached
        assert cloned.isPublic is False
        # The source keeps its content, token, and live URL.
        assert src.token == old_token
        client.force_authenticate(user=None)
        assert client.get(_raw_url(old_token)).status_code == status.HTTP_200_OK

    def test_unpublish_by_source_splits_and_clone_keeps_token(
            self, client, source, dest, source_admin):
        # Accepted semantic change: while a still-public clone shares the content, the
        # source unpublishing detaches ITS row — the original URL keeps serving the
        # clone's copy. Global revocation only exists when no other course shares.
        src, cloned = _shared_file(source, dest)
        old_token = src.token

        client.force_authenticate(user=source_admin)
        resp = client.patch(f"/courseFiles/{src.id}/", {"isPublic": False}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data

        src.refresh_from_db()
        cloned.refresh_from_db()
        assert src.content_id != cloned.content_id
        assert src.isPublic is False
        assert cloned.token == old_token
        client.force_authenticate(user=None)
        resp = client.get(_raw_url(old_token))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.content == b"shared text"

    def test_edit_by_clone_splits(self, client, source, dest, dest_admin):
        src, cloned = _shared_file(source, dest)
        old_token = src.token

        client.force_authenticate(user=dest_admin)
        resp = client.patch(f"/courseFiles/{cloned.id}/", {"data": "edited"}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["data"] == "edited"
        # The editor's copy is public (state carried over) under a FRESH token.
        assert resp.data["isPublic"] is True
        assert str(old_token) not in (resp.data["publicUrl"] or "")

        cloned.refresh_from_db()
        src.refresh_from_db()
        assert cloned.content_id != src.content_id
        assert cloned.content.data == "edited"
        # The source's data and URL are untouched.
        assert src.content.data == "shared text"
        client.force_authenticate(user=None)
        resp = client.get(_raw_url(old_token))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.content == b"shared text"

    def test_publish_shared_private_splits(self, client, source, dest, dest_admin):
        src, cloned = _shared_file(source, dest, public=False)

        client.force_authenticate(user=dest_admin)
        resp = client.patch(f"/courseFiles/{cloned.id}/", {"isPublic": True}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["publicUrl"] is not None

        cloned.refresh_from_db()
        src.refresh_from_db()
        assert cloned.content_id != src.content_id
        assert cloned.isPublic is True
        # Publishing in the clone must not expose the source's file.
        assert src.isPublic is False
        client.force_authenticate(user=None)
        assert client.get(_raw_url(src.token)).status_code == status.HTTP_404_NOT_FOUND
        assert client.get(_raw_url(cloned.token)).status_code == status.HTTP_200_OK

    def test_noop_patch_does_not_split(self, client, source, dest, dest_admin):
        # The UI PATCHes whole objects — an unchanged echo must not trigger a copy.
        src, cloned = _shared_file(source, dest)
        client.force_authenticate(user=dest_admin)
        resp = client.patch(
            f"/courseFiles/{cloned.id}/",
            {"name": cloned.name, "data": "shared text", "isPublic": True,
             "extension": cloned.extension, "course": dest.id},
            format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        cloned.refresh_from_db()
        assert cloned.content_id == src.content_id

    def test_rename_does_not_split(self, client, source, dest, dest_admin):
        # name/path are per-course row attributes; renaming must not copy the content.
        src, cloned = _shared_file(source, dest)
        client.force_authenticate(user=dest_admin)
        resp = client.patch(f"/courseFiles/{cloned.id}/", {"name": "renamed.txt"}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        cloned.refresh_from_db()
        assert cloned.name == "renamed.txt"
        assert cloned.content_id == src.content_id
        src.refresh_from_db()
        assert src.name == "handout.txt"

    def test_exclusive_unpublish_still_rotates_token(self, client, source, source_admin):
        # Regression anchor: with no sharer, unpublish keeps today's revocation exactly.
        from core.tests.factories import CourseFileFactory
        cf = CourseFileFactory(course=source, name="solo.txt", data="solo", isPublic=True)
        old_token = cf.token
        old_content_id = cf.content_id
        client.force_authenticate(user=source_admin)
        resp = client.patch(f"/courseFiles/{cf.id}/", {"isPublic": False}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        cf.refresh_from_db()
        assert cf.content_id == old_content_id  # exclusive: mutate in place, no split
        assert cf.token != old_token
        client.force_authenticate(user=None)
        assert client.get(_raw_url(old_token)).status_code == status.HTTP_404_NOT_FOUND

    def test_oversize_edit_rejected_without_split(self, client, source, dest, dest_admin,
                                                  monkeypatch):
        import core.serializers.file as file_ser
        src, cloned = _shared_file(source, dest)
        monkeypatch.setattr(file_ser, "MAX_COURSE_FILE_SIZE", 10)
        client.force_authenticate(user=dest_admin)
        resp = client.patch(f"/courseFiles/{cloned.id}/", {"data": "x" * 50}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        cloned.refresh_from_db()
        assert cloned.content_id == src.content_id  # validation failed before any copy


class TestDeletionGC:

    def test_delete_one_sharer_content_survives(self, client, source, dest):
        src, cloned = _shared_file(source, dest)
        content_id = src.content_id
        cloned.delete()
        assert CourseFileContent.objects.filter(pk=content_id).exists()
        assert client.get(_raw_url(src.token)).status_code == status.HTTP_200_OK

    def test_delete_last_sharer_deletes_content(self, source, dest):
        src, cloned = _shared_file(source, dest)
        content_id = src.content_id
        cloned.delete()
        src.delete()
        assert not CourseFileContent.objects.filter(pk=content_id).exists()

    def test_course_cascade_gc(self, client, source, dest):
        src, _cloned = _shared_file(source, dest)
        content_id = src.content_id
        dest.delete()
        # Still referenced by the source course — content (and its URL) survive.
        assert CourseFileContent.objects.filter(pk=content_id).exists()
        assert client.get(_raw_url(src.token)).status_code == status.HTTP_200_OK
        source.delete()
        assert not CourseFileContent.objects.filter(pk=content_id).exists()


class TestServingFilename:

    def test_filename_from_lowest_id_sharer(self, client, source, dest, dest_admin):
        src, cloned = _shared_file(source, dest)
        client.force_authenticate(user=dest_admin)
        client.patch(f"/courseFiles/{cloned.id}/", {"name": "renamed.txt"}, format="json")
        client.force_authenticate(user=None)
        resp = client.get(_raw_url(src.token))
        assert resp.status_code == status.HTTP_200_OK
        assert 'handout.txt' in resp["Content-Disposition"]
        src.delete()
        resp = client.get(_raw_url(cloned.token))
        assert resp.status_code == status.HTTP_200_OK
        assert 'renamed.txt' in resp["Content-Disposition"]


class TestFilesEndpointShim:
    """The generic /files/ endpoint reads and writes CourseFile content correctly even
    though the row's inherited data column is empty."""

    def test_files_retrieve_returns_content_data(self, client, source, dest, source_admin):
        src, _cloned = _shared_file(source, dest)
        client.force_authenticate(user=source_admin)
        resp = client.get(f"/files/{src.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["data"] == "shared text"

    def test_files_data_write_routes_through_cow(self, client, source, dest, source_admin):
        src, cloned = _shared_file(source, dest)
        client.force_authenticate(user=source_admin)
        resp = client.patch(f"/files/{src.id}/", {"data": "via files endpoint"}, format="json")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        src.refresh_from_db()
        cloned.refresh_from_db()
        assert src.content.data == "via files endpoint"
        assert cloned.content.data == "shared text"  # the passive sharer kept its copy
        # The write must not land on the dead inherited column.
        assert CourseFile.objects.get(pk=src.pk).data == ""


class TestPromptResolution:

    def test_course_file_variable_resolves_in_both_courses(self, source, dest):
        from core.prompts.variables import VariableContext, substitute_variables
        _shared_file(source, dest, name="style.md", data="Use camelCase.")
        for course in (source, dest):
            ctx = VariableContext(course=course)
            text, used = substitute_variables("Follow {course_file:style.md}.", ctx)
            assert "Use camelCase." in text
            assert used == {"course_file"}
