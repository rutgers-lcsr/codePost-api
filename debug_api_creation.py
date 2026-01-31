
import os
import sys
import django
# Setup Django Environment
sys.path.append('/staff/users/mk1800/Development/codePost-api')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')
django.setup()

from rest_framework.test import APIRequestFactory

from core.models import Assignment, Course, Organization, TestCategory
from core.serializers.testCategory import TestCategorySerializer

def test_creation():
    # Get an assignment
    import uuid
    assignment = Assignment.objects.first()
    if not assignment:
        print("No assignment found. Creating one.")
        org, _ = Organization.objects.get_or_create(name="Debug Org", defaults={'identifier': 'debug-org'})
        course, _ = Course.objects.get_or_create(name="Debug Course", period="F23", organization=org)
        assignment = Assignment.objects.create(name="Debug Assignment", course=course, points=100)

    print(f"Using Assignment ID: {assignment.id}")

    # Case 1: Payload WITH id=-1 (Frontend behavior)
    payload_with_id = {
        'id': -1,
        'name': f'Debug Cat ID {uuid.uuid4().hex[:6]}',
        'assignment': assignment.id,
        'testScript': '',
        'maxPoints': 10,
        'sortKey': 0
    }

    print("\nAttempting creation WITH id=-1...")
    serializer = TestCategorySerializer(data=payload_with_id)
    if serializer.is_valid():
        print("Serializer Valid!")
        try:
            instance = serializer.save()
            print(f"Created instance: {instance.id}")
        except Exception as e:
            print(f"Save failed: {e}")
    else:
        print(f"Serializer Invalid: {serializer.errors}")

    # Case 2: Payload WITHOUT id
    payload_no_id = {
        'name': f'Debug Cat NoID {uuid.uuid4().hex[:6]}',
        'assignment': assignment.id,
        'testScript': '',
        'maxPoints': 10,
        'sortKey': 1
    }

    print("\nAttempting creation WITHOUT id...")
    serializer = TestCategorySerializer(data=payload_no_id)
    if serializer.is_valid():
        print("Serializer Valid!")
        try:
            instance = serializer.save()
            print(f"Created instance: {instance.id}")
        except Exception as e:
            print(f"Save failed: {e}")
    else:
        print(f"Serializer Invalid: {serializer.errors}")

if __name__ == "__main__":
    test_creation()
