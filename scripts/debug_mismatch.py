import os
import django
import sys
# Setup Django environment BEFORE importing anything that uses it
sys.path.append('/staff/users/mk1800/Development/codePost-api')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from core.views.testCategory import TestCategoryViewSet

def test_preview_endpoint_mismatch():
    factory = APIRequestFactory()
    view = TestCategoryViewSet.as_view({'post': 'preview_script'})

    # This is what the frontend is sending (according to my analysis)
    payload_from_frontend = {
        'testScript': '@test(name="Foo", points=1)\ndef f(): pass',
        'language': 'python'
    }
    
    print(f"Testing with payload: {payload_from_frontend}")
    
    request = factory.post('/testCategories/preview-script/', payload_from_frontend, format='json')
    from core.models import User
    # Mock a user and force auth
    user = User.objects.first()
    if not user:
        user = User.objects.create(username='debug_user', email='debug@example.com')
    from rest_framework.test import force_authenticate
    force_authenticate(request, user=user)
    
    response = view(request)
    
    print(f"Response status: {response.status_code}")
    print(f"Response data: {response.data}")
    
    if len(response.data) == 0:
        print("FAILURE CONFIRMED: Backend returned no tests because it expects 'script' but got 'testScript'")
    else:
        print("SUCCESS? Tests detected (hypothesis wrong)")

if __name__ == '__main__':
    test_preview_endpoint_mismatch()
