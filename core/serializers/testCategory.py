from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import TestCategory

class TestCategorySerializer(ModelSerializerWithPOSTCheck):
  class Meta:
    model = TestCategory
    fields = ('id', 'name', 'testCases', 'assignment',)
    POST_permissions_fields = ('assignment',)
    read_only_fields = ('testCases', 'testFiles')
