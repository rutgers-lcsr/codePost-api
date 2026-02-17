import os
import django
from unittest.mock import patch, MagicMock

# Setup Django environment
import sys
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")
django.setup()

from core.models import Assignment, Submission, TestCase, SubmissionTest, User, Course, Organization, TestCategory
from core.models import calculate_grade
from core.tests.factories import CourseFactory, AssignmentFactory, UserFactory, SubmissionFactory

import uuid

def verify_run_tests_on_submit():
    print("Verifying runTestsOnSubmit...")
    
    # Create test data
    unique_suffix = str(uuid.uuid4())[:8]
    course = CourseFactory(name=f"TestCourse_{unique_suffix}")
    assignment = AssignmentFactory(course=course, name="Test Assignment", runTestsOnSubmit=False)
    student = UserFactory(username=f"student_{unique_suffix}")
    
    # Enable global auto-execute setting
    from django.conf import settings
    settings.AUTOGRADER_AUTO_EXECUTE = True
    
    # Mock the task
    with patch('autograder.run.RunSubmission.delay') as mock_run:
        # Create submission (triggers signal)
        print("  Creating submission with runTestsOnSubmit=False...")
        # Use manual creation to ensure signal fires (Factory mutes it)
        submission = Submission(assignment=assignment)
        submission.save() 
        submission.students.add(student)
        
        # Check if task was NOT called
        if mock_run.called:
            print("  FAIL: RunSubmission was called when runTestsOnSubmit=False")
        else:
            print("  PASS: RunSubmission was not called")
            
        # Update assignment to enable auto-execution
        print("  Updating assignment to runTestsOnSubmit=True...")
        assignment.runTestsOnSubmit = True
        assignment.save()
        
        # Create another submission
        print("  Creating submission with runTestsOnSubmit=True...")
        submission2 = Submission(assignment=assignment)
        submission2.save() # This triggers signal created=True
        submission2.students.add(student)
        
        # Check if task WAS called
        if mock_run.called:
             print("  PASS: RunSubmission was called when runTestsOnSubmit=True")
        else:
             print("  FAIL: RunSubmission was NOT called when runTestsOnSubmit=True")
        
        # Check if task WAS called
        if mock_run.called:
             print("  PASS: RunSubmission was called when runTestsOnSubmit=True")
        else:
             print("  FAIL: RunSubmission was NOT called when runTestsOnSubmit=True")

def verify_tests_affect_grade():
    print("\nVerifying testsAffectGrade...")
    
    # Create test data
    unique_suffix = str(uuid.uuid4())[:8]
    course = CourseFactory(name=f"GradeCourse_{unique_suffix}")
    assignment = AssignmentFactory(course=course, name="Grade Assignment", testsAffectGrade=False, points=100)
    student = UserFactory(username=f"student_grade_{unique_suffix}")
    submission = SubmissionFactory(assignment=assignment)
    submission.students.add(student)
    submission.save()
    
    # Create TestCategory and TestCase manually
    category = TestCategory.objects.create(assignment=assignment, name="Default")
    test_case = TestCase.objects.create(
        testCategory=category, 
        pointsPass=10, 
        pointsFail=0, 
        description="Sample Test",
        type="io" # Assuming 'io' is a valid type
    )
    
    # Create a passing test result
    # We need to manually create SubmissionTest because run logic is mocked/skipped
    sub_test = SubmissionTest.objects.create(
        submission=submission,
        testCase=test_case,
        passed=True,
        score=10,
        maxScore=10
    )
    
    # Calculate grade - should NOT include test points
    print("  Calculating grade with testsAffectGrade=False...")
    grade = calculate_grade(submission)
    print(f"  Grade: {grade}")
    
    if grade == 0:
        print("  PASS: Grade is 0 (test points ignored)")
    else:
        print(f"  FAIL: Grade is {grade} (expected 0)")
        
    # Enable testsAffectGrade
    print("  Updating assignment to testsAffectGrade=True...")
    assignment.testsAffectGrade = True
    assignment.save()
    
    print("  Calculating grade with testsAffectGrade=True...")
    grade = calculate_grade(submission)
    print(f"  Grade: {grade}")
    
    if grade == 10:
        print("  PASS: Grade is 10 (test points included)")
    else:
        print(f"  FAIL: Grade is {grade} (expected 10)")

if __name__ == "__main__":
    verify_run_tests_on_submit()
    verify_tests_affect_grade()
