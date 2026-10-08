# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Regression test: a student submission larger than Django's default 2.5 MB
DATA_UPLOAD_MAX_MEMORY_SIZE must not 400 with RequestDataTooBig. The files travel
inline in a JSON body, so the whole body counts against that cap.
"""
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.factories import OrganizationFactory, UserFactory


class TestStudentUploadBodySize(APITestCase):
    def setUp(self):
        org = OrganizationFactory(name="BigOrg", shortname="BO")

        self.admin = UserFactory(username="admin@bo.edu", email="admin@bo.edu")
        self.admin.profile.organization = org
        self.admin.profile.canCreateCourses = True
        self.admin.profile.canModifyRosters = True
        self.admin.save()

        self.student = UserFactory(username="student@bo.edu", email="student@bo.edu")
        self.student.profile.organization = org
        self.student.save()

        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/courses/', {"name": "CS Big", "period": "F2026"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        course_id = resp.data['id']

        resp = self.client.patch(f'/courses/{course_id}/roster/', {"students": [self.student.email]})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        resp = self.client.post('/assignments/', {
            "name": "HW Big",
            "points": 100,
            "state": "published",
            "allowStudentUpload": True,
            "course": course_id,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assignment_id = resp.data['id']

    def test_submission_over_django_default_body_cap_is_accepted(self):
        # Two 2 MB files: each is under the 10 MB per-file limit, but the 4 MB JSON
        # body exceeds Django's 2.5 MB default.
        blob = "x" * (2 * 1024 * 1024)
        self.client.force_authenticate(user=self.student)
        resp = self.client.post(f'/assignments/{self.assignment_id}/studentUpload/', {
            "files": [
                {"name": "a.txt", "data": blob, "extension": ".txt", "path": ""},
                {"name": "b.txt", "data": blob, "extension": ".txt", "path": ""},
            ],
            "sendConfirmationEmail": False,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data['files']), 2)
