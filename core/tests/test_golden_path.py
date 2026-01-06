from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth.models import User
from core.models import Organization, Course, Assignment, Submission, File, RubricCategory, RubricComment
from core.tests.factories import OrganizationFactory, UserFactory

class TestGoldenPath(APITestCase):
    def setUp(self):
        # 1. Setup Organization and Users
        self.org = OrganizationFactory(name="Golden Org", shortname="GO")
        
        # Super Admin
        self.admin = UserFactory(username="admin", email="admin@go.edu")
        self.admin.profile.organization = self.org
        self.admin.profile.canCreateCourses = True
        self.admin.profile.canModifyRosters = True
        self.admin.save()
        
        # Student (initially just a user, will be added to roster)
        self.student = UserFactory(username="student", email="student@go.edu")
        self.student.profile.organization = self.org
        self.student.save()
        
        # Grader (initially just a user)
        self.grader = UserFactory(username="grader", email="grader@go.edu")
        self.grader.profile.organization = self.org
        self.grader.save()

    def test_golden_path_lifecycle(self):
        # 2. Course Creation (Admin)
        # Using the API to verify the "organization not required" fix covers this path
        self.client.force_authenticate(user=self.admin)
        course_data = {
            "name": "CS101 Golden",
            "period": "F2024",
            # Organization omitted, should be inferred
        }
        response = self.client.post('/courses/', course_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        course_id = response.data['id']
        course = Course.objects.get(id=course_id)
        self.assertEqual(course.organization, self.org)
        
        # 3. Roster Management
        # Add Student and Grader
        roster_data = {
            "students": [self.student.email],
            "graders": [self.grader.email]
        }
        response = self.client.patch(f'/courses/{course_id}/roster/', roster_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn(self.student, course.students.all())
        self.assertIn(self.grader, course.graders.all())

        # 4. Assignment Creation (Admin)
        assignment_data = {
            "name": "Homework 1",
            "points": 100,
            "isReleased": True,
            "allowStudentUpload": True,
            "course": course_id
        }
        response = self.client.post('/assignments/', assignment_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        assignment_id = response.data['id']
        assignment = Assignment.objects.get(id=assignment_id)

        # Create Rubric Category and Comment (needed for grading)
        rubric_cat_data = {
            "name": "General",
            "pointLimit": 10,
            "assignment": assignment_id
        }
        response = self.client.post('/rubricCategories/', rubric_cat_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        cat_id = response.data['id']
        
        rubric_com_data = {
            "text": "Minor error",
            "pointDelta": 5.0, # Deduction of 5 points
            "category": cat_id
        }
        response = self.client.post('/rubricComments/', rubric_com_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        rubric_comment_id = response.data['id']
 
        # 5. Student Submission
        self.client.force_authenticate(user=self.student)
        
        # Custom student upload endpoint
        formatted_code = "print('Hello World')"
        upload_data = {
            "files": [
                {
                    "name": "main.py",
                    "data": formatted_code,
                    "extension": ".py",
                    "path": ""
                }
            ],
            "sendConfirmationEmail": False
        }
        response = self.client.post(f'/assignments/{assignment_id}/studentUpload/', upload_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        submission_id = response.data['id']
        
        # 6. Grading (Grader)
        self.client.force_authenticate(user=self.grader)
        
        # Grader must claim the submission to be able to grade it
        response = self.client.get(f'/assignments/{assignment_id}/drawUnassigned/?amount=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # The response is a list of submissions drawn
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], submission_id)
        
        # Get the file ID to attach comment to
        submission = Submission.objects.get(id=submission_id)
        submission_file = submission.files.first()
        
        comment_data = {
            "file": submission_file.id,
            "text": "Nice print statement",
            "pointDelta": 5.0, # Deduction of 5 points
            "rubricComment": rubric_comment_id,
            "startLine": 1,
            "endLine": 1,
            "startChar": 0,
            "endChar": 5
        }
        response = self.client.post('/comments/', comment_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        
        # Finalize Submission
        # Patch the submission to set isFinalized=True
        # Note: Graders might need explicit permissions or just be a grader.
        response = self.client.patch(f'/submissions/{submission_id}/', {"isFinalized": True})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        
        # 7. Verification
        submission.refresh_from_db()
        self.assertTrue(submission.isFinalized)
        # Grade should be calculated (100 - 5 = 95)
        # Note: Assignment default points 100 in my test data, but codePost sometimes defaults to 20 or similar if not set?
        # I passed 100 in assignment creation.
        # Check grade calculation logic. 
        # Usually calculate_grade signal/method runs on save if finalized.
        self.assertEqual(submission.grade, 95.00)

