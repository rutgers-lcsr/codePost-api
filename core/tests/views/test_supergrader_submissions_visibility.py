# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Assignment, Course, Organization, Submission, User


class TestSupergraderSubmissionsVisibility(APITestCase):
    def setUp(self):
        # Users
        self.course_admin = User.objects.create_user(
            username='admin', email='admin@codepost.io', password='password'
        )
        self.supergrader = User.objects.create_user(
            username='supergrader', email='supergrader@codepost.io', password='password'
        )
        self.student1 = User.objects.create_user(
            username='student1', email='student1@codepost.io', password='password'
        )
        self.student2 = User.objects.create_user(
            username='student2', email='student2@codepost.io', password='password'
        )

        # Org + course
        self.organization = Organization.objects.create(name='Rutgers University', shortname='RU')
        self.course = Course.objects.create(name='CS101', period='Fall 2023', organization=self.organization)
        self.course.courseAdmins.add(self.course_admin)
        self.course.superGraders.add(self.supergrader)
        self.course.students.add(self.student1, self.student2)

        # Assignment + submissions
        self.assignment = Assignment.objects.create(name='Homework 1', course=self.course, points=100.0)

        self.sub1 = Submission.objects.create(assignment=self.assignment)
        self.sub1.students.add(self.student1)

        self.sub2 = Submission.objects.create(assignment=self.assignment)
        self.sub2.students.add(self.student2)

    def test_supergrader_can_view_all_assignment_submissions(self):
        self.client.force_authenticate(user=self.supergrader)

        response = self.client.get(f'/assignments/{self.assignment.id}/submissions/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
