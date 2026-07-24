# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for quiz description image upload + public token-based serving."""
import io

import factory
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.signals import post_save
from rest_framework import status


def _png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (2, 2), (255, 0, 0)).save(buf, format='PNG')
    return buf.getvalue()


@pytest.fixture
def img_setup(db, settings, tmp_path):
    # Keep uploaded files out of the repo working tree.
    settings.MEDIA_ROOT = str(tmp_path)
    from core.tests.factories import CourseFactory, AdminFactory
    with factory.django.mute_signals(post_save):
        course = CourseFactory(name="cos240", period="s2026", organization__name="Princeton")
    return {
        'course': course,
        'admin': course.courseAdmins.first(),
        'student': course.students.first(),
        'outsider': AdminFactory(course='other', organization=course.organization, count=99),
    }


def _png_upload():
    return SimpleUploadedFile('diagram.png', _png_bytes(), content_type='image/png')


class TestQuizImageUpload:
    def test_staff_can_upload_and_image_serves_publicly(self, api_client, img_setup):
        from core.models import QuizImage

        api_client.force_authenticate(user=img_setup['admin'])
        resp = api_client.post('/quizImages/', {'course': img_setup['course'].id, 'image': _png_upload()},
                               format='multipart')
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data['url'].endswith(f"/quizImages/raw/{resp.data['token']}/")
        assert QuizImage.objects.filter(course=img_setup['course']).count() == 1

        # The serve endpoint is public — fetch it WITHOUT authentication (as a browser <img> would).
        token = resp.data['token']
        anon = type(api_client)()  # fresh, unauthenticated client
        served = anon.get(f'/quizImages/raw/{token}/')
        assert served.status_code == status.HTTP_200_OK
        assert served['Content-Type'] == 'image/png'
        assert served['X-Content-Type-Options'] == 'nosniff'
        assert b''.join(served.streaming_content) == _png_bytes()

    def test_rejects_non_image(self, api_client, img_setup):
        api_client.force_authenticate(user=img_setup['admin'])
        bad = SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain')
        resp = api_client.post('/quizImages/', {'course': img_setup['course'].id, 'image': bad}, format='multipart')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_student_cannot_upload(self, api_client, img_setup):
        api_client.force_authenticate(user=img_setup['student'])
        resp = api_client.post('/quizImages/', {'course': img_setup['course'].id, 'image': _png_upload()},
                               format='multipart')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_serve_unknown_token_404(self, api_client, img_setup):
        anon = type(api_client)()
        resp = anon.get('/quizImages/raw/00000000-0000-0000-0000-000000000000/')
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_removes_storage_file(self, api_client, img_setup):
        """QuizImage.delete() overrides Django's default (which leaves files behind) to
        remove the stored file — otherwise deleted images accumulate in MEDIA_ROOT/S3."""
        import os
        from core.models import QuizImage
        api_client.force_authenticate(user=img_setup['admin'])
        resp = api_client.post('/quizImages/', {'course': img_setup['course'].id, 'image': _png_upload()},
                               format='multipart')
        assert resp.status_code == status.HTTP_201_CREATED
        image = QuizImage.objects.get(pk=resp.data['id'])
        path = image.image.path
        assert os.path.exists(path)

        resp = api_client.delete(f"/quizImages/{image.id}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not QuizImage.objects.filter(pk=image.pk).exists()
        assert not os.path.exists(path)
