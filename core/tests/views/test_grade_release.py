import json
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from core.models import Course, Assignment, Submission, Organization, Section
from rest_framework import status

class GradeReleaseTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org", shortname="TO")
        self.course = Course.objects.create(name="CS101", period="F2021", organization=self.org)
        self.student = User.objects.create_user(username="student", email="student@test.com", password="password")
        self.course.students.add(self.student)
        
        self.assignment = Assignment.objects.create(
            name="Test Assignment",
            course=self.course,
            isReleased=True, # Assignment is released for submission
            feedbackReleased=False, # Grades are NOT released
            points=100
        )
        
        self.submission = Submission.objects.create(
            assignment=self.assignment,
            isFinalized=False, 
            grade=95
        )
        self.submission.students.add(self.student)
        self.submission.isFinalized = True
        self.submission.save()
        
        # Authenticate as student
        self.client.force_authenticate(user=self.student)

    def test_submission_details_masked_when_submissions_unreleased(self):
        """
        Verify that isFinalized is masked (False) and grade is hidden when feedbackReleased is False.
        """
        url = f'/submissions/{self.submission.id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['isFinalized'], "isFinalized should be False when feedbackReleased is False")
        self.assertIsNone(response.data.get('grade'), "Grade should be None/Hidden")

    def test_submission_details_visible_when_submissions_released(self):
        """
        Verify that isFinalized is True and grade is visible when feedbackReleased is True.
        """
        self.assignment.feedbackReleased = True
        self.assignment.save()
        
        url = f'/submissions/{self.submission.id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['isFinalized'], "isFinalized should be True when feedbackReleased is True")
        self.assertEqual(float(response.data['grade']), 100.0, "Grade should be visible")

    def test_submission_details_visible_if_live_feedback(self):
        """
        Verify that details are visible if liveFeedbackMode is True, even if feedbackReleased is False.
        """
        self.assignment.liveFeedbackMode = True
        self.assignment.feedbackReleased = False
        self.assignment.save()
        
        url = f'/submissions/{self.submission.id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # In live feedback mode, students see isFinalized as it is (True) or False?
        # Current logic: line 377 in views/submission.py:
        # if not assignment.submissionsReleased and not liveFeedback: mask
        # elif not isFinalized and not liveFeedback: status
        # else: full details.
        
        # So if liveFeedback is True, it falls through to "else: returns StudentSubmissionSerializer".
        # Which shows isFinalized and grade.
        self.assertTrue(response.data['isFinalized'])
        self.assertEqual(float(response.data['grade']), 100.0)

    def test_list_submissions_masked(self):
        """
        Verify listing submissions also masks data.
        """
        url = f'/assignments/{self.assignment.id}/submissions/?student={self.student.email}'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) > 0)
        sub_data = response.data[0]
        self.assertFalse(sub_data['isFinalized'])
        self.assertIsNone(sub_data.get('grade'))

