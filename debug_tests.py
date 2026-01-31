
import os
import django
import sys
import inspect

# Setup Django environment
sys.path.append('/staff/users/mk1800/Development/codePost-api')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")
django.setup()

from core.models import Submission, TestCase, SubmissionTest, File
from autograder.services.TestService import TestService
from autograder.services.executors.python import PythonNotebookExecutor
from autograder.services.executors.base import Executor
import autograder

def inspect_latest_submission():
    print(f"DEBUG: autograder is loaded from: {autograder.__file__}")

    # 1. Check NotebookExecutor.execute source code (Wait, I edited NotebookExecutor!)
    from autograder.services.executors.base import NotebookExecutor
    print("=" * 40)
    print("Checking NotebookExecutor.execute source code in memory...")
    try:
        src = inspect.getsource(NotebookExecutor.execute)
        # Check for DEBUG_EXEC log
        if "DEBUG_EXEC" in src:
            print("CONFIRMED: DEBUG_EXEC is present in NotebookExecutor.execute")
        else:
            print("WARNING: DEBUG_EXEC is NOT present in NotebookExecutor.execute")
            print("Preview of source:")
            print(src[:200])
    except Exception as e:
        print(f"Failed to inspect NotebookExecutor.execute: {e}")

    # 2. Check Template Content
    print("=" * 40)
    print("Checking Notebook Template Content...")
    try:
        mock_file = File(name="test.ipynb", extension=".ipynb")
        executor = PythonNotebookExecutor(mock_file)
        # Manually call _get_code_template (mocking args as empty strings since we just want to read the file)
        # Note: Depending on impl, it might need real args. 
        # PythonNotebookExecutor._get_code_template calls super()._get_code_template() then does replace.
        # If we just want file content, we can call Base method? No, strictly verify what PythonNotebookExecutor uses.
        template = executor._get_code_template("CODE", [], "")
        if "SYNTAX ERROR" in template:
            print("CONFIRMED: Syntax Error is present in loaded template.")
        else:
            print("WARNING: Syntax Error is NOT present in loaded template.")
            print("Preview:")
            print(template[:100])
    except Exception as e:
        print(f"Failed to check template: {e}")

    # 3. Running Execution
    print("=" * 40)
    print("Running Manual Execution...")
    submission_id = 111
    try:
        # We want to run ONLY the jupyter test case to isolate logs
        target_name = "jupyter_random_test.ipynb"
        test_case = TestCase.objects.filter(fileName=target_name).first()
        
        if not test_case:
             print(f"Jupyter test case not found!")
             return

        # FIXED TEST CODE INJECTION
        print("Injecting correct @test decorator into Jupyter Test Case...")
        TEST_CODE_FIX = """
@test()
def test_random_tensor():
    # Assuming np is imported in notebook, but let's be safe if we can, 
    # or rely on shared scope if notebook imported it.
    # The user code was: assert(np.all( random_tensor( (10,10) ) >= 0))
    # So random_tensor and np should be there.
    tensor = random_tensor((10,10))
    assert np.all(tensor >= 0)
"""
        test_case.testCode = TEST_CODE_FIX
        test_case.save()
        print("-> TestCase updated with valid test methods.")

        print(f"Running ONLY test case {test_case.id} ({target_name})...")
        results = TestService.run_suite(submission_id, test_case_ids=[test_case.id])
        
        print(f"Run Suite Returned {len(results)} results:")
        for r in results:
             success = r.get('success')
             passed = r.get('passed')
             print(f"  Test: {r.get('testCaseId')} | Success: {success} | Passed: {passed}")
             if not success:
                 print(f"  Error: {r.get('error')}")

        # Verify DB logs
        target_names = ["jupyter_random_test.ipynb", "python.py"]
        test_cases = TestCase.objects.filter(fileName__in=target_names)
        
        for t in test_cases:
             result = SubmissionTest.objects.filter(submission__id=submission_id, testCase=t).first()
             if result:
                 print(f"  DB Check - Test: {t.fileName} | Modified: {result.modified} | Passed: {result.passed}")
                 print("-" * 10 + " LOGS START " + "-" * 10)
                 print(result.logs)
                 print("-" * 10 + " LOGS END " + "-" * 10)
    except Exception as e:
        print(f"Execution Error: {e}")

if __name__ == "__main__":
    inspect_latest_submission()
