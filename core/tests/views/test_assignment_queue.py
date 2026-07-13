# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.test import TestCase
from core.models import Assignment, Course, Section, Submission, User, Organization
from rest_framework.test import APIClient
from rest_framework import status

class TestAssignmentQueue(TestCase):

    def setUp(self):
        # Create Users
        self.course_admin = User.objects.create_user(username='admin', email='admin@codepost.io', password='password')
        self.grader = User.objects.create_user(username='grader', email='grader@codepost.io', password='password')
        self.supergrader = User.objects.create_user(username='supergrader', email='supergrader@codepost.io', password='password')
        self.student1 = User.objects.create_user(username='student1', email='student1@codepost.io', password='password')
        self.student2 = User.objects.create_user(username='student2', email='student2@codepost.io', password='password')
        
        # Create Organization
        self.organization = Organization.objects.create(name='Rutgers University', shortname='RU')
        
        # Create Course
        self.course = Course.objects.create(name='CS101', period='Fall 2023', organization=self.organization)
        self.course.courseAdmins.add(self.course_admin)
        self.course.graders.add(self.grader)
        self.course.superGraders.add(self.supergrader)
        self.course.students.add(self.student1, self.student2)
        
        # Create Sections
        self.section1 = Section.objects.create(name='Section 1', course=self.course)
        self.section2 = Section.objects.create(name='Section 2', course=self.course)
        self.section1.students.add(self.student1)
        self.section2.students.add(self.student2)

        # Create Assignment
        self.assignment = Assignment.objects.create(name='Homework 1', course=self.course, points=100.0)

        # Create Submissions
        self.sub1 = Submission.objects.create(assignment=self.assignment)
        self.sub1.students.add(self.student1)
        
        self.sub2 = Submission.objects.create(assignment=self.assignment)
        self.sub2.students.add(self.student2)
        
        self.client = APIClient()

    def test_queue_length_basic(self):
        self.client.force_authenticate(user=self.grader)
        url = f'/assignments/{self.assignment.id}/queueLength/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Use unclaimed instead of queueLength
        self.assertEqual(response.data['unclaimed'], 2)
        self.assertEqual(response.data['id'], self.assignment.id)

    def test_queue_length_with_section_filter(self):
        self.client.force_authenticate(user=self.grader)
        
        # Filter by Section 1 (should have 1 submission: student1)
        url = f'/assignments/{self.assignment.id}/queueLength/?section={self.section1.id}'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unclaimed'], 1)
        
        # Filter by Section 2 (should have 1 submission: student2)
        url = f'/assignments/{self.assignment.id}/queueLength/?section={self.section2.id}'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unclaimed'], 1)
        
        # Filter by both sections (should have 2 submissions)
        url = f'/assignments/{self.assignment.id}/queueLength/?section={self.section1.id}&section={self.section2.id}'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unclaimed'], 2)

    def test_queue_length_updates_on_claim(self):
        self.client.force_authenticate(user=self.grader)
        
        # Initial check
        url = f'/assignments/{self.assignment.id}/queueLength/'
        response = self.client.get(url)
        self.assertEqual(response.data['unclaimed'], 2)
        
        # Claim one submission
        self.sub1.grader = self.grader
        self.sub1.save()
        
        # Check again
        response = self.client.get(url)
        self.assertEqual(response.data['unclaimed'], 1)
        self.assertEqual(response.data['unfinalized'], 1) # claimed but not finalized

    def test_queue_length_updates_on_unclaim(self):
        self.client.force_authenticate(user=self.grader)
        
        # Start with one claimed
        self.sub1.grader = self.grader
        self.sub1.save()
        
        url = f'/assignments/{self.assignment.id}/queueLength/'
        response = self.client.get(url)
        self.assertEqual(response.data['unclaimed'], 1)
        
        # Unclaim
        self.sub1.grader = None
        self.sub1.save()
        
        # Check again
        response = self.client.get(url)
        self.assertEqual(response.data['unclaimed'], 2)

    def test_queue_length_accessible_to_supergrader(self):
        self.client.force_authenticate(user=self.supergrader)

        url = f'/assignments/{self.assignment.id}/queueLength/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unclaimed'], 2)
