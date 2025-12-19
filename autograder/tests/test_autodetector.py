from django.test import TestCase
from core.models import Submission, Assignment, Course, Environment, SubmissionFile
from autograder.services.autodetector import Autodetector

class AutodetectorTest(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="Test Course", period="Fall 2025")
        self.assignment = Assignment.objects.create(course=self.course, name="Test Assignment")
        self.environment = Environment.objects.create(assignment=self.assignment, auto_detect=True, language="other")
        self.submission = Submission.objects.create(assignment=self.assignment)

    def test_detect_python(self):
        SubmissionFile.objects.create(submission=self.submission, name="main.py", data="print('hello')", extension="py")
        
        updated = Autodetector.detect_and_update(self.submission)
        
        self.assertTrue(updated)
        self.environment.refresh_from_db()
        self.assertEqual(self.environment.language, "python3")

    def test_detect_java(self):
        SubmissionFile.objects.create(submission=self.submission, name="Main.java", data="class Main {}", extension="java")
        
        updated = Autodetector.detect_and_update(self.submission)
        
        self.assertTrue(updated)
        self.environment.refresh_from_db()
        self.assertEqual(self.environment.language, "java")

    def test_no_update_if_auto_detect_false(self):
        self.environment.auto_detect = False
        self.environment.save()
        
        SubmissionFile.objects.create(submission=self.submission, name="main.py", data="print('hello')", extension="py")
        
        updated = Autodetector.detect_and_update(self.submission)
        
        self.assertFalse(updated)
        self.environment.refresh_from_db()
        self.assertEqual(self.environment.language, "other")
