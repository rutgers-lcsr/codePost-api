
import os
import django
from django.conf import settings

# Configure minimal Django settings
if not settings.configured:
    settings.configure(INSTALLED_APPS=['rest_framework', 'core'])
    django.setup()

from rest_framework import serializers

class TestSerializer(serializers.Serializer):
    targetFilename = serializers.CharField(source='target_filename')
    contextFileId = serializers.IntegerField(source='context_file_id', required=False)

data = {'targetFilename': 'test.py', 'contextFileId': 123}
serializer = TestSerializer(data=data)
if serializer.is_valid():
    print("Validated Data Keys:", list(serializer.validated_data.keys()))
    print("Validated Data:", serializer.validated_data)
else:
    print("Errors:", serializer.errors)
