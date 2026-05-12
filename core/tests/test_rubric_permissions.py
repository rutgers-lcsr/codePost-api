# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.

from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Course, Assignment, RubricCategory, Organization
from rest_framework.test import APIClient
from core.permissions.helpers import isRubricEditor
from core.serializers.course import CourseRosterSerializer

class RubricPermissionsTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", shortname="TO")
        self.course = Course.objects.create(name="CS101", period="F2023", organization=self.org)
        self.assignment = Assignment.objects.create(name="A1", course=self.course, points=100.0)
        self.category = RubricCategory.objects.create(name="General", assignment=self.assignment)
        
        self.admin = User.objects.create_user(username="admin", email="admin@test.com", password="password")
        self.course.courseAdmins.add(self.admin)
        
        self.grader = User.objects.create_user(username="grader", email="grader@test.com", password="password")
        self.course.graders.add(self.grader)
        
        self.rubric_editor = User.objects.create_user(username="editor", email="editor@test.com", password="password")
        self.course.graders.add(self.rubric_editor)
        self.course.rubricEditors.add(self.rubric_editor)
        
        self.client = APIClient()

    def test_isRubricEditor_helper(self):
        self.assertTrue(isRubricEditor(self.rubric_editor, self.course))
        self.assertFalse(isRubricEditor(self.grader, self.course))

    def test_rubric_category_permissions(self):
        # Authenticate as rubric editor
        self.client.force_authenticate(user=self.rubric_editor)
        
        # Test PATCH (write access)
        _response = self.client.patch(f'/rubricCategories/{self.category.id}/', {'name': 'Updated Name'})
        # Note: Actual response depends on view implementation, but permission check happens first. 
        # If permission denied, it would be 403. If allowed (but maybe other errors), it won't be 403.
        # However, checking permission class directly is more robust if we don't want to rely on full view set up.
        
        # Let's verify via the helper and knowing the permission logic manually first
        from core.permissions.permissions import RubricCategoryPermissions
        perm = RubricCategoryPermissions()
        
        # Mock request/view
        class MockRequest:
            def __init__(self, user, method):
                self.user = user
                self.method = method
                
        # Test Rubric Editor
        self.assertTrue(perm.has_object_permission(MockRequest(self.rubric_editor, "PATCH"), None, self.category))
        
        # Test Regular Grader
        self.assertFalse(perm.has_object_permission(MockRequest(self.grader, "PATCH"), None, self.category))
        
        # Test Course Admin
        self.assertTrue(perm.has_object_permission(MockRequest(self.admin, "PATCH"), None, self.category))

    def test_serializer_rubric_editor_assignment(self):
        # Test that we can assign rubric editor via serializer
        data = {
            'organization': self.org.id,
            'name': self.course.name,
            'period': self.course.period,
            'students': [],
            'graders': [self.grader.email],
            'rubricEditors': [self.grader.email],
            'courseAdmins': [self.admin.email],
            'superGraders': []
        }
        
        # Mock request with admin user
        request = type('Request', (object,), {'user': self.admin})
        
        serializer = CourseRosterSerializer(instance=self.course, data=data, context={'request': request}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        
        self.assertTrue(self.course.rubricEditors.filter(email=self.grader.email).exists())
        
    def test_serializer_validation_non_grader(self):
        # Test that assigning a non-grader as rubric editor fails validation logic (it basically filters them out)
        student = User.objects.create_user(username="student", email="student@test.com")
        
        data = {
            'graders': [self.grader.email], # student is NOT in graders
            'rubricEditors': [student.email], # Trying to make student a rubric editor
            'courseAdmins': [self.admin.email]
        }
         # Mock request with admin user
        request = type('Request', (object,), {'user': self.admin})
        
        serializer = CourseRosterSerializer(instance=self.course, data=data, context={'request': request}, partial=True)
        self.assertTrue(serializer.is_valid()) 
        # The validation logic in serializer removes non-graders from rubricEditors list, so it remains valid but empty for that field
        validated_data = serializer.validated_data
        self.assertEqual(len(validated_data['rubricEditors']), 0)

