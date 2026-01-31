#!/usr/bin/env python
"""
Debug script to check all TestCases for an assignment and their configuration.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')
django.setup()

from core.models import Submission, SubmissionTest, TestCase, TestCategory, Assignment
from decimal import Decimal

print("=" * 60)
print("DEBUGGING TEST CONFIGURATION")
print("=" * 60)

# Get recent submission
sub = Submission.objects.order_by('-modified').first()
if not sub:
    print("No submissions found!")
    sys.exit(1)

print(f"\nSubmission ID: {sub.id}")
print(f"Assignment: {sub.assignment.name}")
print(f"Current Grade: {sub.grade}")
print(f"isFinalized: {sub.isFinalized}")
print(f"gradeFrozen: {sub.gradeFrozen}")

# Get all TestCases for this assignment
test_categories = sub.assignment.testCategories.all()
print(f"\n--- Test Categories: {test_categories.count()} ---")

all_test_cases = []
for cat in test_categories:
    print(f"\nCategory: {cat.name}")
    for tc in cat.testCases.all():
        all_test_cases.append(tc)
        print(f"  TestCase ID: {tc.id}")
        print(f"    Description: {tc.description}")
        print(f"    Type: {tc.type}")
        print(f"    pointsPass: {tc.pointsPass}")
        print(f"    pointsFail: {tc.pointsFail}")
        
        # Check if there's a SubmissionTest for this
        st = SubmissionTest.objects.filter(submission=sub, testCase=tc).first()
        if st:
            print(f"    -> SubmissionTest: passed={st.passed}, score={st.score}, maxScore={st.maxScore}")
        else:
            print(f"    -> SubmissionTest: NOT RUN")

# Calculate expected grade contribution from tests
print("\n" + "=" * 60)
print("GRADE CALCULATION BREAKDOWN")
print("=" * 60)

from core.models import getLatestSubmissionTests, calculate_grade

tests = list(getLatestSubmissionTests(sub))
print(f"\nLatest SubmissionTests: {len(tests)}")

counter = 0
for test in tests:
    if test.maxScore and test.maxScore > 0:
        ratio = float(test.score) / float(test.maxScore)
        contribution = ratio * float(test.testCase.pointsPass)
        print(f"  {test.testCase.description}: {test.score}/{test.maxScore} * {test.testCase.pointsPass} = {contribution:.2f}")
    else:
        if test.passed:
            contribution = float(test.testCase.pointsPass)
            print(f"  {test.testCase.description}: PASSED -> {contribution:.2f}")
        else:
            contribution = float(test.testCase.pointsFail)
            print(f"  {test.testCase.description}: FAILED -> {contribution:.2f}")
    counter += contribution

print(f"\nTotal test contribution: {counter:.2f}")
print(f"Expected grade: {calculate_grade(sub)}")
print(f"Current grade in DB: {sub.grade}")
