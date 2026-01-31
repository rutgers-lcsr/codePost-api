from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import TestCategoryResource
from core.serializers.file import AssignmentFileSerializer
from core.serializers.assignmentDataSet import AssignmentDataSetSerializer

class TestCategoryResourceSerializer(ModelSerializerWithPOSTCheck):
  # Nested read-only fields for detailed display
  file_details = AssignmentFileSerializer(source='file', read_only=True)
  dataset_details = AssignmentDataSetSerializer(source='dataset', read_only=True)

  class Meta:
    model = TestCategoryResource
    fields = ('id', 'category', 'file', 'dataset', 'target_path', 'file_details', 'dataset_details')
    POST_permissions_fields = ('category',)
