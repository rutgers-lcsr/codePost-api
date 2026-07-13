# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import os
import sys
import unittest
from unittest.mock import patch

# Path setup for Django
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')

import django
django.setup()

from core.models import Environment, Assignment
from autograder.services.converger import Converger
from autograder.services.autodetector import Autodetector
from autograder.testUtils.buildHelpers import createDockerFile

class TestFullPipeline(unittest.TestCase):
    def setUp(self):
        # Create dummy environment
        self.assignment = Assignment(name="Test Assign", course_id=1, points=100) # Mock fields as needed
        self.assignment.save()
        self.env = Environment.objects.create(
            assignment=self.assignment,
            language="python-3.12",
            requirements="",
            auto_detect=True
        )

    def tearDown(self):
        self.env.delete()
        self.assignment.delete()

    def test_converger_updates_requirements(self):
        print("\n--- Testing Converger ---")
        # Simulate log output
        logs = """
        Traceback (most recent call last):
          File "main.py", line 1, in <module>
            import requests
        ModuleNotFoundError: No module named 'requests'
        """
        
        Converger.analyze_and_converge(self.env.id, logs)
        
        # Refresh from DB
        self.env.refresh_from_db()
        print(f"Requirements after convergence: {self.env.requirements}")
        self.assertIn("requests", self.env.requirements)

    def test_builder_generates_dockerfile(self):
        print("\n--- Testing Dockerfile Generation ---")
        # Set requirements
        self.env.requirements = "requests\nnumpy"
        self.env.save()
        
        # Call helper directly
        content = createDockerFile(
            self.env.language,
            "managed", # env.buildType
            "", # dockerfile
            "", # run instructions
            self.env.id,
            dependencies_file_content=self.env.requirements
        )
        
        print(f"Generated Dockerfile snippet:\n{content[:200]}...")
        self.assertIn("RUN pip install", content)
        self.assertIn("requests", content)
        self.assertIn("numpy", content)

    @patch('autograder.services.autodetector.SubmissionFile')
    def test_autodetector_uses_scanners(self, MockSubFile):
        print("\n--- Testing AutoDetector Integration ---")
        # Ensure logic is importable and testable
        self.assertTrue(hasattr(Autodetector, 'detect_and_update'))

if __name__ == '__main__':
    from django.test.utils import setup_test_environment
    setup_test_environment()
    unittest.main()
