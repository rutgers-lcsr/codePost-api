
import os
import django
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")
django.setup()

from core.models import Course, Assignment
from core.services.ai_service import AIService

class TestAIRubricIntegration(unittest.TestCase):
    def test_rubric_injection(self):
        # Setup Mock Course & Assignment
        course = MagicMock(spec=Course)
        course.ai_provider = 'gemini'
        course.ai_api_key = 'test_key'
        course.ai_model = 'gemini-pro'
        
        assignment = MagicMock(spec=Assignment)
        assignment.ai_system_prompt = None # Use default
        
        service = AIService(course, assignment)
        
        # Monkeypatch _call_gemini to inspect prompt
        # _call_gemini is async
        captured_system_prompt = []
        
        async def mock_call_gemini(system_prompt, user_prompt):
            captured_system_prompt.append(system_prompt)
            return "```python\nprint('Hello World')\n```"
            
        service._call_gemini = mock_call_gemini
        
        # Execute
        rubric_text = "Verify that the function handles negative inputs correctly."
        
        # We need to run async method synchronously
        from asgiref.sync import async_to_sync
        result = async_to_sync(service.generate_test_script)(
            context_file_content="def foo(x): return x",
            context_filename="main.py",
            target_filename="test_main.py",
            rubric_text=rubric_text
        )
        
        # Verify
        self.assertTrue(result.success)
        self.assertEqual(len(captured_system_prompt), 1)
        
        prompt = captured_system_prompt[0]
        print("\n--- Captured System Prompt ---\n")
        print(prompt)
        print("\n------------------------------\n")
        
        expected_fragment = f"Rubric Criterion (Test Goal):\n{rubric_text}"
        
        if expected_fragment in prompt:
            print("SUCCESS: Rubric text found in prompt.")
        else:
            print("FAILURE: Rubric text NOT found in prompt.")
            self.fail("Rubric text missing from prompt")

if __name__ == '__main__':
    unittest.main()
