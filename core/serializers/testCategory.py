from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import TestCategory

from core.serializers.testCategoryResource import TestCategoryResourceSerializer

class TestCategorySerializer(ModelSerializerWithPOSTCheck):
  resources = TestCategoryResourceSerializer(many=True, read_only=True)

  class Meta:
    model = TestCategory
    fields = ('id', 'name', 'testCases', 'assignment', 'testScript', 'maxPoints', 'sortKey', 'targetFileName', 'resources')
    POST_permissions_fields = ('assignment',)
    read_only_fields = ('testCases', 'testFiles', 'resources')

