import os
import django
import sys
import json

# Setup Django environment
sys.path.append('/staff/users/mk1800/Development/codePost-api')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')
django.setup()

from core.models import TestCategory
from autograder.services.TestParsingService import TestParsingService

def test_preview_logic():
    # Simulate the exact scenario:
    # 1. Script content that should work
    script_content = """
@test(name="My Test", points=10)
def test_example():
    pass
"""
    language = "python"
    
    print(f"Testing with script:\n{script_content}")
    print(f"Language: {language}")

    # mimic the view logic in testCategory.py
    mock_category = TestCategory(testScript=script_content)
    
    try:
        parsed_tests = TestParsingService.parse_script(mock_category, language=language)
        print(f"Parsed tests count: {len(parsed_tests)}")
        for t in parsed_tests:
            print(t)
            
        if len(parsed_tests) == 0:
            print("FAILURE: No tests detected.")
        else:
            print("SUCCESS: Tests detected.")

    except Exception as e:
        print(f"Error parsing script: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_preview_logic()
