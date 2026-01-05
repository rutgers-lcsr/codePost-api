import django
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")
django.setup()

from core.models import *
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from django.urls import reverse
from django.utils.timezone import now
from django.conf import settings
settings.ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

def run_test():
    # Setup
    print("Setting up data...")
    org, _ = Organization.objects.get_or_create(name="Test Org", defaults={"shortname":"TO"})
    course, _ = Course.objects.get_or_create(name="Test Course", defaults={"period":"Fall 2025", "organization":org})
    
    # Assignment: Visible but NOT Released
    assignment, _ = Assignment.objects.get_or_create(
        course=course, name="Test Assignment",
        defaults={
            "isVisible":True, "isReleased":False,
            "allowStudentUpload":True,
            "points":100
        }
    )
    # Ensure isReleased is False (in case it existed and was True)
    assignment.isReleased = False
    assignment.save()
    
    student, _ = User.objects.get_or_create(username="student", defaults={"email":"student@test.com", "password":"password"})
    grader, _ = User.objects.get_or_create(username="grader", defaults={"email":"grader@test.com", "password":"password"})
    
    course.students.add(student)
    course.graders.add(grader)
    
    # Student uploads
    # Find existing submission or create
    submission = Submission.objects.filter(assignment=assignment, students__in=[student]).first()
    if not submission:
        submission = Submission.objects.create(assignment=assignment, dateUploaded=now())
        submission.students.add(student)
    
    # Grader finalizes
    submission.grader = grader
    submission.isFinalized = True
    submission.save()
    
    print(f"DEBUG: Submission students: {[s.email for s in submission.students.all()]}")
    print(f"DEBUG: Request user: {student.email}")
    
    print(f"Submission {submission.id} is finalized. Assignment isReleased={assignment.isReleased}")
    
    # Test visibility
    client = APIClient()
    client.force_authenticate(user=student)
    
    url = f"/api/submissions/{submission.id}/"
    check_perm_url = f"/api/submissions/{submission.id}/checkPermission/"
    
    print(f"Requesting {check_perm_url} as student...")
    response = client.get(check_perm_url)
    print(f"CheckPermission Status: {response.status_code}")
    if response.status_code == 200:
        print(f"CheckPermission Data: {response.data}")

    print(f"Requesting {url} as student...")
    response = client.get(url)
    
    print(f"Response status: {response.status_code}")
    if response.status_code == 200:
        print("Response data:", response.data)
        
    if response.status_code == 403:
        print("Student CANNOT see submission (Correct behavior for unreleased).")
    else:
        print("Student CAN see submission (Incorrect if we want to hide it).")

    # Now release
    assignment.isReleased = True
    assignment.save()
    print("Assignment released.")
    
    response = client.get(url)
    print(f"Response status after release: {response.status_code}")
    if response.status_code == 200:
        print("Student CAN see submission now.")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(e)
