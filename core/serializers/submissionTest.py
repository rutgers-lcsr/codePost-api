from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import SubmissionTest

class SubmissionTestSerializer(ModelSerializerWithPOSTCheck):
  testCategory = serializers.ReadOnlyField(source='testCase.testCategory.id')

  class Meta:
    model = SubmissionTest
    fields = ('id', 'submission', 'testCase', 'logs', 'passed', 'testCategory', 'created', 'modified', 'isError')
    POST_permissions_fields = ('submission',)
    read_only_fields = ('testCategory', 'modified', 'created', )
