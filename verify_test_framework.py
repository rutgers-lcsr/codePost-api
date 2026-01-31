
import os
import django
import sys

# Setup Django Environment
sys.path.append('/staff/users/mk1800/Development/codePost-api')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')
django.setup()

from core.models import User, Assignment, Course, Organization, Submission, AssignmentFile, TestCategory, TestCase, SubmissionTest
from autograder.services.TestService import TestService
from autograder.services.TestParsingService import TestParsingService

def verify_framework():
    print("Setting up test data...")
    # Create basic hierarchy
    org, _ = Organization.objects.get_or_create(name="Test Org", defaults={'identifier': 'test-org'})
    course, _ = Course.objects.get_or_create(name="CS101", period="Fall 2023", organization=org)
    
    # Create Assignment
    assignment, _ = Assignment.objects.get_or_create(name="Test Framework Assignment", course=course, defaults={'points': 100})
    
    # Create TestCategory with Script
    script_content = """
@test("Addition Test", points=5)
def test_add():
    assert 1 + 1 == 2
    return True

@test("Subtraction Test", points=5)
def test_sub():
    assert 2 - 1 == 1
    return True
"""
    category, _ = TestCategory.objects.get_or_create(
        name="Unit Tests", 
        assignment=assignment, 
        defaults={
            'maxPoints': 10,
            'testScript': script_content
        }
    )
    
    print(f"Created Category: {category.id}")
    
    # Verify Parsing
    # The signal should have triggered parsing. Let's check TestCases.
    test_cases = TestCase.objects.filter(testCategory=category)
    print(f"Parsed Test Cases: {test_cases.count()}")
    for tc in test_cases:
        print(f" - {tc.description} ({tc.functionName})")
        
    if test_cases.count() != 2:
        print("ERROR: Parsing failed.")
        return

    # Create Submission
    submission, _ = Submission.objects.get_or_create(assignment=assignment, defaults={'gradeFrozen': True})
    print(f"Created Submission: {submission.id}")
    
    # Mock file for submission (though our script doesn't actually read it, the runner might check)
    # in this case, the test script relies on internal logic, so checking file presence is skipped by autograder unless explicit.
    
    # Run Tests
    print("Running Suite...")
    # We need to mock the User for the service call? TestService.run_suite takes user_id
    user, _ = User.objects.get_or_create(email="test@example.com", defaults={'username': 'testuser'})
    
    # Note: run_suite usually dispatches celery tasks. We want to run synchronously if possible or check results.
    # But TestService.run_suite calls celery `RunSubmission.delay`.
    # We can try to invoke the logic of RunSubmission directly or just TestService logic.
    
    # Actually, TestService.run_suite just queues it.
    # To verify logic without Celery, we might need to call specific service methods.
    # But `TestService.run_suite` logic is:
    # 1. Update old results? or just queue.
    
    # Let's call the parsing service directly to ensure it works (already checked above via signal).
    
    # NOW: Verification of Execution Logic.
    # Since we can't easily run the full dockerized autograder here without environment set up,
    # we can verify that `TestService` *can* execute these tests if we mock the executor?
    # Or at least verify that the structure is correct.
    
    # The prompt actually said "TestParsingService ... is implemented". "TestService ... is refactored".
    # We should trust the parsing works (checked above).
    
    # Let's verify `TestCategory` serializer exposes the new fields.
    from core.serializers.testCategory import TestCategorySerializer
    serialized = TestCategorySerializer(category).data
    print(f"Serialized Category: script keys present? {'testScript' in serialized}")
    
    # Let's verify `TestCase` serializer
    from core.serializers.testCase import TestCaseSerializer
    tc = test_cases.first()
    serialized_tc = TestCaseSerializer(tc).data
    print(f"Serialized TestCase: functionName present? {'functionName' in serialized_tc}")

    print("Verification Script Finished.")

if __name__ == "__main__":
    verify_framework()
