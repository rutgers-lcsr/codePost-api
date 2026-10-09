# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Upload size limits, end to end through the API:

- the whole-request cap (DATA_UPLOAD_MAX_MEMORY_SIZE) answers as a JSON 413, not
  Django's HTML 400, and sits above a multi-file submission;
- per-file caps are measured in decoded bytes, so a base64 PDF gets the same 10 MB
  a .py file does;
- a submission has a total cap; /assignmentFiles/ and /submissionFiles/ enforce the
  per-file cap too; /system/uploadLimits/ publishes the numbers the UI pre-checks with.
"""
import base64

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from core import constants
from core.tests.factories import OrganizationFactory, UserFactory

MIB = 1024 * 1024


def pdf_data_uri(num_bytes):
    # Real %PDF magic so File.save's MIME signature check passes.
    return 'data:application/pdf;base64,' + base64.b64encode(b'%PDF-1.4\n' + b'\0' * (num_bytes - 9)).decode()


class TestUploadSizeLimits(APITestCase):
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
        self.course_id = resp.data['id']

        resp = self.client.patch(f'/courses/{self.course_id}/roster/', {"students": [self.student.email]})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        resp = self.client.post('/assignments/', {
            "name": "HW Big",
            "points": 100,
            "state": "published",
            "allowStudentUpload": True,
            "course": self.course_id,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assignment_id = resp.data['id']

    def student_upload(self, files):
        self.client.force_authenticate(user=self.student)
        return self.client.post(f'/assignments/{self.assignment_id}/studentUpload/', {
            "files": files,
            "sendConfirmationEmail": False,
        }, format='json')

    # --- whole-request cap -------------------------------------------------

    def test_submission_over_django_default_body_cap_is_accepted(self):
        # Two 2 MB files: each is under the 10 MB per-file limit, but the 4 MB JSON
        # body exceeds Django's 2.5 MB default.
        blob = "x" * (2 * MIB)
        resp = self.student_upload([
            {"name": "a.txt", "data": blob, "extension": ".txt", "path": ""},
            {"name": "b.txt", "data": blob, "extension": ".txt", "path": ""},
        ])
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data['files']), 2)

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=1024)
    def test_body_over_cap_is_json_413(self):
        resp = self.student_upload([
            {"name": "a.txt", "data": "x" * 4096, "extension": ".txt", "path": ""},
        ])
        self.assertEqual(resp.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertEqual(resp['Content-Type'].split(';')[0], 'application/json')
        self.assertIn('Upload too large', resp.data['detail'])
        self.assertIn(str(constants.MAX_REQUEST_BODY_BYTES // MIB), resp.data['detail'])

    def test_layers_are_ordered(self):
        # A maximal submission (base64-inflated) must fit the request cap, and the
        # request cap must equal what nginx is configured with.
        self.assertLessEqual(constants.MAX_SUBMISSION_TOTAL_SIZE * 4 // 3 + MIB, constants.MAX_REQUEST_BODY_BYTES)
        self.assertLessEqual(constants.MAX_COURSE_FILE_SIZE * 4 // 3 + MIB, constants.MAX_REQUEST_BODY_BYTES)
        for fn in ('nginx.conf', 'nginx.conf.template'):
            with open(fn) as fh:
                self.assertIn(f"client_max_body_size {constants.MAX_REQUEST_BODY_BYTES // MIB}M;", fh.read(), fn)

    # --- per-file cap, measured in decoded bytes ----------------------------

    def test_binary_file_just_under_limit_is_accepted(self):
        # ~13.2 MB on the wire; would be rejected if we counted base64 characters.
        resp = self.student_upload([
            {"name": "report.pdf", "data": pdf_data_uri(constants.MAX_FILE_SIZE - 1024),
             "extension": ".pdf", "path": ""},
        ])
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_binary_file_over_limit_is_rejected_by_name(self):
        resp = self.student_upload([
            {"name": "report.pdf", "data": pdf_data_uri(constants.MAX_FILE_SIZE + 1024),
             "extension": ".pdf", "path": ""},
        ])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertEqual(resp.data['file'], 'report.pdf')
        self.assertIn('10MB', str(resp.data['error']))

    def test_submission_total_over_limit_is_rejected(self):
        per_file = constants.MAX_FILE_SIZE - MIB
        count = constants.MAX_SUBMISSION_TOTAL_SIZE // per_file + 1
        resp = self.student_upload([
            {"name": f"f{i}.txt", "data": "x" * per_file, "extension": ".txt", "path": ""}
            for i in range(count)
        ])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn('total size limit', str(resp.data))

    def test_assignment_file_over_limit_points_at_datasets(self):
        resp = self.client.post('/assignmentFiles/', {
            "name": "big.bin", "extension": ".bin", "path": "", "assignment": self.assignment_id,
            "data": pdf_data_uri(constants.MAX_ASSIGNMENT_FILE_SIZE + 1024),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        msg = str(resp.data)
        self.assertIn("big.bin", msg)
        self.assertIn("dataset", msg)

    def test_submission_file_over_limit_is_rejected(self):
        resp = self.student_upload([{"name": "a.txt", "data": "x", "extension": ".txt", "path": ""}])
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        submission_id = resp.data['id']
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/submissionFiles/', {
            "name": "huge.txt", "extension": ".txt", "path": "", "submission": submission_id,
            "data": "x" * (constants.MAX_FILE_SIZE + 1024),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn("huge.txt", str(resp.data))

    # --- limits endpoint ----------------------------------------------------

    def test_upload_limits_endpoint(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.get('/system/uploadLimits/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data, {
            'maxSubmissionFileBytes': constants.MAX_FILE_SIZE,
            'maxSubmissionTotalBytes': constants.MAX_SUBMISSION_TOTAL_SIZE,
            'maxAssignmentFileBytes': constants.MAX_ASSIGNMENT_FILE_SIZE,
            'maxCourseFileBytes': constants.MAX_COURSE_FILE_SIZE,
            'maxDatasetBytes': constants.MAX_DATASET_SIZE,
            'maxQuizImageBytes': constants.MAX_QUIZ_IMAGE_SIZE,
            'maxRequestBodyBytes': constants.MAX_REQUEST_BODY_BYTES,
        })

    def test_upload_limits_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/system/uploadLimits/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
