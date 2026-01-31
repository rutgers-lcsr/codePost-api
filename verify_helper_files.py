import os
import django
import sys
from unittest.mock import patch, MagicMock

# Setup Django Environment
sys.path.append('/staff/users/mk1800/Development/codePost-api')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')
django.setup()

from core.models import User, Assignment, Course, Organization, Submission, AssignmentFile, TestCategory, TestCase, File, SubmissionFile
from autograder.services.TestService import TestService
from autograder.services.executors import Executor

def verify_helper_files():
    print("Setting up test data...")
    org, _ = Organization.objects.get_or_create(name="Test Org", defaults={'identifier': 'test-org'})
    course, _ = Course.objects.get_or_create(name="CS101", period="Fall 2023", organization=org)
    assignment, _ = Assignment.objects.get_or_create(name="File Override Assignment", course=course, defaults={'points': 100})

    # 1. Create Helper File
    helper_content = "def test_func():\n    return 'Overridden'"
    helper_file, _ = AssignmentFile.objects.get_or_create(
        name="helper.py", 
        assignment=assignment,
        defaults={
            'data': helper_content,
            'extension': 'py',
            'hidden': True
        }
    )
    print(f"Created Helper File: {helper_file.name} (Hidden: {helper_file.hidden})")

    # 2. Create TestCategory with Helper File
    script_content = """
@test("Override Test", points=10)
def test_override():
    import helper
    assert helper.test_func() == 'Overridden'
    return True
"""
    category, _ = TestCategory.objects.get_or_create(
        name="Helper Test Category", 
        assignment=assignment, 
        defaults={
            'testScript': script_content
        }
    )
    # Update script to trigger parsing
    category.testScript = script_content
    category.save()
    
    # Add helper file
    category.helperFiles.add(helper_file)
    print(f"Added helper file to category. Count: {category.helperFiles.count()}")

    # 3. Create Submission
    # Patch calculate_grade to avoid ID error during creation
    with patch('core.models.calculate_grade', return_value=0):
        submission, _ = Submission.objects.get_or_create(assignment=assignment)
    
    # Ensure submission has at least one file to target
    sub_file, _ = SubmissionFile.objects.get_or_create(
        name="main.py", 
        submission=submission,
        defaults={'data': 'print("Student Code")', 'extension': 'py'}
    )
    
    # 4. Mock Executor.factory and run test
    test_case = TestCase.objects.filter(testCategory=category).first()
    if not test_case:
        print("Error: No test case parsed.")
        return

    print(f"Running test case: {test_case.functionName}")
    
    # Note: We need to patch where TestService IMPORTS Executor, or the class itself.
    # Identifying correct path: autograder.services.TestService.Executor
    with patch('autograder.services.TestService.Executor.factory') as mock_factory:
        mock_executor = MagicMock()
        mock_factory.return_value = mock_executor
        mock_executor.execute.return_value = MagicMock(success=True, stdout="", stderr="", output_data={}, tests=[])
        
        TestService.run_test(test_case.id, submission.id)
        
        # Verify factory call
        if mock_factory.called:
            args, kwargs = mock_factory.call_args
            print("Executor.factory called with:")
            print(f" - additional_files passed? {'additional_files' in kwargs}")
            
            if 'additional_files' in kwargs:
                files = kwargs['additional_files']
                print(f" - additional_files length: {len(files)}")
                if len(files) > 0:
                    print(f" - First file: {files[0].name}")
                    if files[0].id == helper_file.id:
                        print("SUCCESS: Correct helper file passed!")
                    else:
                        print(f"FAILURE: Wrong file passed. Expected {helper_file.id}, got {files[0].id}")
                else:
                    print("FAILURE: Empty additional_files list.")
            else:
                print("FAILURE: additional_files not passed to factory.")
        else:
             print("FAILURE: Executor.factory was not called.")

if __name__ == "__main__":
    verify_helper_files()
