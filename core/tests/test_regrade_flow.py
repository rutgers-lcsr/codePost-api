# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework.test import APITestCase
from rest_framework import status
from core.tests.factories import OrganizationFactory, UserFactory


class TestRegradeFlow(APITestCase):
    """
    End-to-end test for the regrade request flow:
    1. Setup course with grader, student, and assignment (allowRegradeRequests=True)
    2. Student submits, grader grades and finalizes
    3. Student opens a regrade request
    4. Grader fetches submissions via compact+grader params — verifies regrade fields are present
    5. Grader responds to the regrade request
    6. Verify the regrade is marked as closed
    """

    def setUp(self):
        self.org = OrganizationFactory(name="Regrade Org", shortname="RO")

        self.admin = UserFactory(username="regrade_admin", email="admin@ro.edu")
        self.admin.profile.organization = self.org
        self.admin.profile.canCreateCourses = True
        self.admin.profile.canModifyRosters = True
        self.admin.save()

        self.grader = UserFactory(username="regrade_grader", email="grader@ro.edu")
        self.grader.profile.organization = self.org
        self.grader.save()

        self.student = UserFactory(username="regrade_student", email="student@ro.edu")
        self.student.profile.organization = self.org
        self.student.save()

    def test_regrade_request_lifecycle(self):
        # 1. Admin creates course, roster, assignment
        self.client.force_authenticate(user=self.admin)

        response = self.client.post('/courses/', {"name": "Regrade Course", "period": "S2026"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        course_id = response.data['id']

        response = self.client.patch(f'/courses/{course_id}/roster/', {
            "students": [self.student.email],
            "graders": [self.grader.email],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        response = self.client.post('/assignments/', {
            "name": "Regrade HW",
            "points": 100,
            "isReleased": True,
            "allowStudentUpload": True,
            "allowRegradeRequests": True,
            "course": course_id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        assignment_id = response.data['id']

        # Create rubric for grading
        response = self.client.post('/rubricCategories/', {
            "name": "General",
            "pointLimit": 10,
            "assignment": assignment_id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 2. Student submits
        self.client.force_authenticate(user=self.student)
        response = self.client.post(f'/assignments/{assignment_id}/studentUpload/', {
            "files": [{"name": "main.py", "data": "print('hello')", "extension": ".py", "path": ""}],
            "sendConfirmationEmail": False,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        submission_id = response.data['id']

        # 3. Grader claims and finalizes
        self.client.force_authenticate(user=self.grader)
        response = self.client.get(f'/assignments/{assignment_id}/drawUnassigned/?amount=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 1)

        response = self.client.patch(f'/submissions/{submission_id}/', {"isFinalized": True})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # 4. Student opens regrade request via dedicated endpoint
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(f'/submissions/{submission_id}/submitRegrade/', {
            "questionIsRegrade": True,
            "questionText": "I believe my answer on question 3 was graded incorrectly.",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['questionIsOpen'])
        self.assertEqual(response.data['questionText'], "I believe my answer on question 3 was graded incorrectly.")

        # 5. Grader fetches submissions with compact+grader params (the endpoint RegradesPanel uses)
        self.client.force_authenticate(user=self.grader)
        response = self.client.get(
            f'/assignments/{assignment_id}/submissions/',
            {'compact': '1', 'grader': self.grader.email},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Response should be a list (no pagination when page param absent)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)

        sub_data = response.data[0]
        self.assertEqual(sub_data['id'], submission_id)
        self.assertTrue(sub_data['questionIsOpen'])
        self.assertTrue(sub_data['questionIsRegrade'])
        self.assertEqual(sub_data['questionText'], "I believe my answer on question 3 was graded incorrectly.")

        # Compact response should NOT include nested files
        self.assertNotIn('files', sub_data)

        # 6. Grader responds to the regrade
        self.client.force_authenticate(user=self.grader)
        response = self.client.patch(f'/submissions/{submission_id}/', {
            "questionIsOpen": False,
            "questionResponse": "The grade is correct, the question asked for X not Y.",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data['questionIsOpen'])
        self.assertEqual(response.data['questionResponse'], "The grade is correct, the question asked for X not Y.")

        # 7. Verify the regrade is closed when grader re-fetches
        response = self.client.get(
            f'/assignments/{assignment_id}/submissions/',
            {'compact': '1', 'grader': self.grader.email},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        sub_data = response.data[0]
        self.assertFalse(sub_data['questionIsOpen'])
        self.assertNotEqual(sub_data['questionResponse'], '')

    def test_submissions_endpoint_grader_filter(self):
        """Verify that grader param filters to only that grader's submissions."""
        self.client.force_authenticate(user=self.admin)

        response = self.client.post('/courses/', {"name": "Filter Course", "period": "S2026"})
        course_id = response.data['id']

        grader2 = UserFactory(username="grader2", email="grader2@ro.edu")
        grader2.profile.organization = self.org
        grader2.save()

        self.client.patch(f'/courses/{course_id}/roster/', {
            "students": [self.student.email],
            "graders": [self.grader.email, grader2.email],
        })

        response = self.client.post('/assignments/', {
            "name": "Filter HW",
            "points": 50,
            "isReleased": True,
            "allowStudentUpload": True,
            "course": course_id,
        })
        assignment_id = response.data['id']

        # Student uploads
        self.client.force_authenticate(user=self.student)
        response = self.client.post(f'/assignments/{assignment_id}/studentUpload/', {
            "files": [{"name": "sol.py", "data": "x=1", "extension": ".py", "path": ""}],
            "sendConfirmationEmail": False,
        }, format='json')
        _submission_id = response.data['id']

        # Grader1 claims
        self.client.force_authenticate(user=self.grader)
        self.client.get(f'/assignments/{assignment_id}/drawUnassigned/?amount=1')

        # Grader1 fetches with own filter — should see 1
        response = self.client.get(
            f'/assignments/{assignment_id}/submissions/',
            {'compact': '1', 'grader': self.grader.email},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        # Grader2 fetches with own filter — should see 0
        self.client.force_authenticate(user=grader2)
        response = self.client.get(
            f'/assignments/{assignment_id}/submissions/',
            {'compact': '1', 'grader': grader2.email},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_submissions_endpoint_forbidden_for_wrong_grader(self):
        """A grader cannot use the grader filter to see another grader's submissions."""
        self.client.force_authenticate(user=self.admin)

        response = self.client.post('/courses/', {"name": "Forbidden Course", "period": "S2026"})
        course_id = response.data['id']

        grader2 = UserFactory(username="grader3", email="grader3@ro.edu")
        grader2.profile.organization = self.org
        grader2.save()

        self.client.patch(f'/courses/{course_id}/roster/', {
            "students": [self.student.email],
            "graders": [self.grader.email, grader2.email],
        })

        response = self.client.post('/assignments/', {
            "name": "Forbidden HW", "points": 50, "isReleased": True,
            "allowStudentUpload": True, "course": course_id,
        })
        assignment_id = response.data['id']

        # Grader2 tries to see grader1's submissions — should be forbidden
        self.client.force_authenticate(user=grader2)
        response = self.client.get(
            f'/assignments/{assignment_id}/submissions/',
            {'compact': '1', 'grader': self.grader.email},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
