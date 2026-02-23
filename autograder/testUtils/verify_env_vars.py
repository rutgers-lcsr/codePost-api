# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.

import os
import django
import sys
import shutil
import unittest

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")
django.setup()

from core.models import Environment, Assignment, Course, Period, Organization
from autograder.testUtils.buildHelpers import createDockerFile

class TestEnvVars(unittest.TestCase):
    def setUp(self):
        # Clean up old assignments
        Assignment.objects.filter(name="EnvVarTest").delete()
        Course.objects.filter(name="TestCourseEnv").delete()

        # Create Dependencies
        self.org, _ = Organization.objects.get_or_create(name="TestOrgEnv", defaults={"shortname": "TOE"})
        # Period is just a string in the model shown in context?!
        # Let's check model definition again...
        # Line 184: period = models.CharField(max_length=32...) 
        # Ah, so period is a string, not a FK?
        # Wait, verify_full_pipeline used course_id=1.
        
        self.course = Course.objects.create(name="TestCourseEnv", organization=self.org, period="F2023")
        
        self.assignment = Assignment.objects.create(name="EnvVarTest", points=100, course=self.course)
        self.env = Environment.objects.create(
            assignment=self.assignment,
            language="python-3.12",
            env_vars={"API_KEY": "12345", "DEBUG": "true"}
        )

    def tearDown(self):
        self.env.delete()
        self.assignment.delete()
        self.course.delete()
        # self.org.delete() # Keep org to avoid cascade issues if shared

    def test_persistence(self):
        """Test that env_vars are saved and retrieved correctly."""
        env_refetched = Environment.objects.get(id=self.env.id)
        self.assertEqual(env_refetched.env_vars, {"API_KEY": "12345", "DEBUG": "true"})
        print("[PASS] Persistence Verified")

    def test_dockerfile_generation(self):
        """Test that createDockerFile injects ENV commands."""
        
        # Verify helper function direct call
        content = createDockerFile(
            language=self.env.language,
            build_type="default",
            env_vars=self.env.env_vars
        )
        
        print("\nGenerated Dockerfile Content:\n", content)

        self.assertIn('ENV API_KEY="12345"', content)
        self.assertIn('ENV DEBUG="true"', content)
        print("[PASS] Dockerfile ENV Injection Verified")

if __name__ == "__main__":
    from django.test.utils import setup_test_environment
    setup_test_environment()
    unittest.main()
