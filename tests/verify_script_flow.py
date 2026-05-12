# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.

import os
import django
import sys
import json
from unittest.mock import MagicMock

# Setup Django environment
sys.path.append('/staff/users/mk1800/Development/codePost-api')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')
django.setup()

from core.models import TestCase, File
from core.services.ai_service import AIService
from autograder.services.TestService import TestService

def verify_end_to_end():
    print("1. Setting up Dummy Files and Objects...")
    
    # Create a dummy target file
    target_filename = "target.py"
    with open(target_filename, "w") as f:
        f.write("def foo(): return 1\nprint('Hello World')")
        
    # Mock File object
    # The Executor generally uses file.name to determine type, and might use file path or content.
    # In local dev mode, it might look for the file on disk or expect we handle it.
    # Let's see if we can trick it.
    mock_file = MagicMock(spec=File)
    mock_file.name = target_filename
    mock_file.path = os.path.abspath(target_filename)
    # Some executors access file.file.path
    mock_file.file = MagicMock()
    mock_file.file.path = os.path.abspath(target_filename)
    
    # Create in-memory TestCase (script type)
    script_content = """
import json
print(json.dumps({"tests": [{"name": "Test 1", "passed": True, "score": 1.0, "max_score": 1.0, "output": "It works!"}]}))
"""
    # Note: We structure output as 'tests' list because verify_script_test expects that format
    # from the executor result. The executor for 'script' type (CustomScriptExecutor?) 
    # should parse the script output (JSON) and put it into 'tests' key.
    
    test_case = TestCase(
        type='script',
        testCode=script_content,
        fileName=target_filename,
        description="Verify Script Test"
    )
    
    print(f"2. Running Ephemeral Execution...")
    
    try:
        # We need to ensure the correct executor is picked.
        # target.py -> PythonExecutor?
        # But if type='script', TestService._run_ephemeral_execution calls:
        # ExecutorClass = get_executor_class(file.name)
        # -> PythonExecutor.
        # valid.
        # Then executor = ExecutorClass(..., test_code=test_case.testCode)
        # The PythonExecutor needs to handle `test_code` and execute it ONLY (or alongside??).
        # Implemention Plan said: "Update run_test dispatch: If type == 'script', use _run_ephemeral_execution... Inject testCode".
        # And "PythonExecutor to inject the new template.py".
        
        # If the PythonExecutor supports `test_code`, it should use the generic runner or template.
        
        result = TestService._run_ephemeral_execution(mock_file, test_case)
        
        print("3. Execution Result (Raw):")
        print(json.dumps(result, indent=2, default=str))
        
        # Verify
        final_verification = TestService.verify_script_test(test_case, result)
        print("\n4. Final Verification:")
        print(json.dumps(final_verification, indent=2))
        
        if final_verification['passed']:
            print("SUCCESS: Script executed and passed.")
        else:
            print("FAILURE: Script failed verification.")
            
    except Exception as e:
        print(f"FAILURE during execution: {e}")
        import traceback
        traceback.print_exc()

    # Clean up
    if os.path.exists(target_filename):
        os.remove(target_filename)
        
    # Verify AI Service call (mocked response logic check)
    print("\n5. Verifying AI Generation Logic (Mocked)...")
    try:
        assert hasattr(AIService, 'generate_test_script')
        print("SUCCESS: AIService.generate_test_script exists.")
    except Exception as e:
        print(f"FAILURE: {e}")

if __name__ == "__main__":
    verify_end_to_end()
