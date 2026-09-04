# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.test import APITestCase
from rest_framework import status
from core.tests.factories import OrganizationFactory, UserFactory


class TestConsoleDataEndpoint(APITestCase):
    """
    Tests for the GET /submissions/{id}/consoleData/ bulk endpoint.
    Verifies response shape, nested comments with rubricComment objects,
    and permission-based serializer selection.
    """

    def setUp(self):
        self.org = OrganizationFactory(name="ConsoleOrg", shortname="CO")

        self.admin = UserFactory(username="admin@co.edu", email="admin@co.edu")
        self.admin.profile.organization = self.org
        self.admin.profile.canCreateCourses = True
        self.admin.profile.canModifyRosters = True
        self.admin.save()

        self.grader = UserFactory(username="grader@co.edu", email="grader@co.edu")
        self.grader.profile.organization = self.org
        self.grader.save()

        self.student = UserFactory(username="student@co.edu", email="student@co.edu")
        self.student.profile.organization = self.org
        self.student.save()

        self.outsider = UserFactory(username="outsider@co.edu", email="outsider@co.edu")
        self.outsider.profile.organization = self.org
        self.outsider.save()

        # Create course, assignment, submission, file, rubric, comment via API
        self.client.force_authenticate(user=self.admin)

        resp = self.client.post('/courses/', {"name": "CS Console", "period": "F2025"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.course_id = resp.data['id']

        resp = self.client.patch(f'/courses/{self.course_id}/roster/', {
            "students": [self.student.email],
            "graders": [self.grader.email],
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        resp = self.client.post('/assignments/', {
            "name": "HW Console",
            "points": 100,
            "state": "published",
            "allowStudentUpload": True,
            "course": self.course_id,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assignment_id = resp.data['id']

        # Create rubric category + comment
        resp = self.client.post('/rubricCategories/', {
            "name": "Style",
            "pointLimit": 10,
            "assignment": self.assignment_id,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.rubric_cat_id = resp.data['id']

        resp = self.client.post('/rubricComments/', {
            "text": "Missing semicolon",
            "pointDelta": -2.0,
            "category": self.rubric_cat_id,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.rubric_comment_id = resp.data['id']

        # Student uploads
        self.client.force_authenticate(user=self.student)
        resp = self.client.post(f'/assignments/{self.assignment_id}/studentUpload/', {
            "files": [
                {"name": "main.py", "data": "print('hello')", "extension": ".py", "path": ""},
                {"name": "util.py", "data": "def helper(): pass", "extension": ".py", "path": ""},
            ],
            "sendConfirmationEmail": False,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.submission_id = resp.data['id']

        # Grader claims + adds a comment with rubric link
        self.client.force_authenticate(user=self.grader)
        resp = self.client.get(f'/assignments/{self.assignment_id}/drawUnassigned/?amount=1')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        from core.models import Submission
        submission = Submission.objects.get(id=self.submission_id)
        self.file_id = submission.files.first().id

        resp = self.client.post('/comments/', {
            "file": self.file_id,
            "text": "Fix this",
            "pointDelta": -2.0,
            "rubricComment": self.rubric_comment_id,
            "startLine": 1,
            "endLine": 1,
            "startChar": 0,
            "endChar": 5,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.comment_id = resp.data['id']

        # Also add a plain comment (no rubric)
        resp = self.client.post('/comments/', {
            "file": self.file_id,
            "text": "Looks good here",
            "pointDelta": 0,
            "startLine": 1,
            "endLine": 1,
            "startChar": 0,
            "endChar": 5,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.plain_comment_id = resp.data['id']

    # ── Staff access: full SubmissionConsoleDataSerializer ──

    def test_admin_gets_full_console_data(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f'/submissions/{self.submission_id}/consoleData/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self._assert_staff_shape(resp.data)

    def test_grader_gets_full_console_data(self):
        self.client.force_authenticate(user=self.grader)
        resp = self.client.get(f'/submissions/{self.submission_id}/consoleData/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self._assert_staff_shape(resp.data)

    def _assert_staff_shape(self, data):
        """Verify the shape of the SubmissionConsoleDataSerializer response."""
        # Top-level fields
        self.assertEqual(data['id'], self.submission_id)
        self.assertIn('assignment', data)
        self.assertIn('students', data)
        self.assertIn('grader', data)
        self.assertIn('isFinalized', data)
        self.assertIn('grade', data)
        self.assertIn('dateEdited', data)
        self.assertIn('files', data)
        self.assertIn('tests', data)

        # Files are full objects with nested comments
        files = data['files']
        self.assertGreaterEqual(len(files), 2)

        # Find the file that has comments
        commented_file = next(f for f in files if f['id'] == self.file_id)
        self.assertIn('comments', commented_file)
        self.assertIn('data', commented_file)
        self.assertIn('name', commented_file)

        comments = commented_file['comments']
        self.assertEqual(len(comments), 2)

        # Find the rubric-linked comment
        rubric_comment = next(c for c in comments if c['id'] == self.comment_id)
        self.assertEqual(rubric_comment['text'], "Fix this")
        self.assertEqual(rubric_comment['startLine'], 1)
        self.assertEqual(rubric_comment['endLine'], 1)
        self.assertIn('author', rubric_comment)

        # Rubric comment is a nested object, not just an ID
        rc = rubric_comment['rubricComment']
        self.assertIsInstance(rc, dict, "rubricComment should be a nested object, not an ID")
        self.assertEqual(rc['id'], self.rubric_comment_id)
        self.assertEqual(rc['text'], "Missing semicolon")
        self.assertIn('pointDelta', rc)

        # The plain comment has rubricComment=null
        plain_comment = next(c for c in comments if c['id'] == self.plain_comment_id)
        self.assertIsNone(plain_comment['rubricComment'])

    # ── Student access: StudentConsoleDataSerializer ──

    def test_student_gets_console_data_no_feedback(self):
        """Before feedback is released, student gets files without comments, grade masked."""
        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f'/submissions/{self.submission_id}/consoleData/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        # Should have files
        self.assertIn('files', resp.data)
        self.assertGreaterEqual(len(resp.data['files']), 2)

        # Grade should be masked (feedbackReleased is False by default)
        self.assertIsNone(resp.data['grade'])

        # Files should have empty comments (feedback not released)
        for f in resp.data['files']:
            self.assertEqual(f['comments'], [], f"File {f['name']} should have no comments before feedback release")

        # Should NOT have grader field (student serializer uses hasGrader)
        self.assertIn('hasGrader', resp.data)

    def test_student_gets_comments_after_feedback_released(self):
        """After feedback is released + finalized, student sees comments."""
        # Finalize and release feedback
        self.client.force_authenticate(user=self.admin)

        from core.models import Assignment
        assignment = Assignment.objects.get(id=self.assignment_id)
        assignment.feedbackStatus = 'released'
        assignment.save()

        # Finalize the submission via grader
        self.client.force_authenticate(user=self.grader)
        resp = self.client.patch(f'/submissions/{self.submission_id}/', {"isFinalized": True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        self.client.force_authenticate(user=self.student)
        resp = self.client.get(f'/submissions/{self.submission_id}/consoleData/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        # Now files should have nested comments with rubric objects
        commented_file = next(f for f in resp.data['files'] if f['id'] == self.file_id)
        self.assertEqual(len(commented_file['comments']), 2)

        rubric_comment = next(c for c in commented_file['comments'] if c['id'] == self.comment_id)
        rc = rubric_comment['rubricComment']
        self.assertIsInstance(rc, dict)
        self.assertEqual(rc['id'], self.rubric_comment_id)

        # Grade should now be visible
        self.assertIsNotNone(resp.data['grade'])

    # ── Permission checks ──

    def test_outsider_gets_403(self):
        """User not in the course gets forbidden."""
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(f'/submissions/{self.submission_id}/consoleData/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_gets_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(f'/submissions/{self.submission_id}/consoleData/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_nonexistent_submission_gets_404(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get('/submissions/99999/consoleData/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
