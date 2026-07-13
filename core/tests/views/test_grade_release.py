# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from core.models import Course, Assignment, Submission, Organization
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

    def test_submission_visible_but_grade_hidden_when_feedback_unreleased(self):
        """
        Students can always see their submission (isFinalized shows true value),
        but grade is hidden when feedbackReleased is False.
        """
        url = f'/submissions/{self.submission.id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # isFinalized should show TRUE value so students know their submission exists
        self.assertTrue(response.data['isFinalized'], "isFinalized should show true value")
        # Grade should be masked to None
        self.assertIsNone(response.data.get('grade'), "Grade should be None/Hidden when feedbackReleased is False")

    def test_submission_and_grade_visible_when_feedback_released(self):
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
        self.assertTrue(response.data['isFinalized'])
        self.assertEqual(float(response.data['grade']), 100.0)

    def test_list_submissions_grade_hidden(self):
        """
        Verify listing submissions shows true isFinalized but hides grade when feedback not released.
        """
        url = f'/assignments/{self.assignment.id}/submissions/?student={self.student.email}'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) > 0)
        sub_data = response.data[0]
        # isFinalized shows true value
        self.assertTrue(sub_data['isFinalized'])
        # Grade is hidden
        self.assertIsNone(sub_data.get('grade'))
