
import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")
django.setup()

from core.models import File, User, Submission, Assignment, Course, Organization
from autograder.services.TestService import TestService

def verify_overrides():
    print("Setting up test data...")
    
    # Create necessary objects directly
    org, _ = Organization.objects.get_or_create(name="Test Org", defaults={"shortname": "testorg_verify"})
    course, _ = Course.objects.get_or_create(name="cs101", period="f2020", organization=org)
    assignment, _ = Assignment.objects.get_or_create(name="Test Assignment Verify", defaults={"course": course})
    user, _ = User.objects.get_or_create(username="grader_verify@test.edu", defaults={"email": "grader_verify@test.edu"})
    submission = Submission.objects.create(assignment=assignment, grader=user) # Always create new submission to avoid file conflicts
    
    # 1. Create Main File (main.py) that imports helper
    main_code = "import helper\nprint(helper.greet())"
    main_file = File.objects.create(
        name="main.py", 
        data=main_code
    )
    # Manual link to submission (M2M or Reverse FK?)
    # Submission.files is a M2M through SubmissionFile?
    # No, SubmissionFile is a model that likely links them.
    # Let's check model structure. 
    # autograder/services/TestService.py:103: submission_files = list(submission.files.all())
    # So submission.files is a ManyToMany or Reverse FK.
    # core/models.py likely has SubmissionFile intermediate or File has FK?
    # API Infastructure says "File Types (polymorphic): SubmissionFile... all inherit File"
    # "SubmissionFile ... ForeignKey to Submission"
    
    # So we need to create SubmissionFile (which is a File subclass)
    from core.models import SubmissionFile
    
    main_file = SubmissionFile.objects.create(
        name="main.py", 
        data=main_code,
        submission=submission
    )

    # 2. Create Helper File (helper.py)
    helper_code = "def greet():\n    return 'Hello Original'"
    helper_file = SubmissionFile.objects.create(
        name="helper.py", 
        data=helper_code, 
        submission=submission
    )

    print(f"Created submission {submission.id} with files: {main_file.id} (main), {helper_file.id} (helper)")

    # 3. Test WITHOUT overrides (Baseline)
    class DummyTestCase:
        testCode = ""
        image_name = None
        functionName = "test"
        type = "script" # Force ephemeral
        id = 999
        def __init__(self):
            pass
    
    dummy_test = DummyTestCase()

    print("\n--- Test 1: Baseline (No Overrides) ---")
    result = TestService._run_ephemeral_execution(main_file, dummy_test)
    print(f"Stdout: {result.get('stdout', '').strip()}")
    if "Hello Original" in result.get('stdout', ''):
        print("PASS: Baseline worked.")
    else:
        print("FAIL: Baseline failed.")

    # 4. Test WITH Helper Override (Int Keys)
    print("\n--- Test 2: Helper Override (Int Keys) ---")
    # Override helper to say 'Hello Override'
    overrides_int = {
        helper_file.id: "def greet():\n    return 'Hello Override'"
    }
    result_int = TestService._run_ephemeral_execution(main_file, dummy_test, file_overrides=overrides_int)
    print(f"Stdout: {result_int.get('stdout', '').strip()}")
    
    if "Hello Override" in result_int.get('stdout', ''):
        print("PASS: Helper override respected.")
    else:
        print("FAIL: Helper override ignored.")

    # 5. Test WITH Helper Override (String Keys) - Simulating Celery
    print("\n--- Test 3: Helper Override (String Keys) ---")
    overrides_str = {
        str(helper_file.id): "def greet():\n    return 'Hello StringKeys'"
    }
    result_str = TestService._run_ephemeral_execution(main_file, dummy_test, file_overrides=overrides_str)
    print(f"Stdout: {result_str.get('stdout', '').strip()}")

    if "Hello StringKeys" in result_str.get('stdout', ''):
        print("PASS: String keys sanitized and override respected.")
    else:
        print("FAIL: String keys failed.")

if __name__ == "__main__":
    try:
        verify_overrides()
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
