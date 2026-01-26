from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import TestCase


class TestCaseSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = TestCase
    fields = ('id', 'testCategory', 'sortKey', 'description', 'type', 'pointsFail', 'pointsPass', 'text', 'modified', 'fileName',
              'exposed', 'instances', 'explanation', 'lastSolutionRun', 'dataSet', 'testCode', 'targetCellId', 'rubricItem')
    POST_permissions_fields = ('testCategory',)
    read_only_fields = ('modified', 'instances',)
    extra_kwargs = {"text": {"trim_whitespace": False}, "description": {
        "trim_whitespace": False}, "explanation": {"trim_whitespace": False}}


class TestCaseStudentSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = TestCase
    fields = ('id', 'testCategory', 'sortKey', 'description', 'pointsFail', 'pointsPass', 'explanation', 'exposed')
    POST_permissions_fields = ('testCategory',)
    extra_kwargs = {"description": {"trim_whitespace": False}, "explanation": {"trim_whitespace": False}}
