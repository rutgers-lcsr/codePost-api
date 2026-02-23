# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import SubmissionTest

class SubmissionTestSerializer(ModelSerializerWithPOSTCheck):
  testCategory = serializers.ReadOnlyField(source='testCase.testCategory.id')

  class Meta:
    model = SubmissionTest
    fields = ('id', 'submission', 'testCase', 'logs', 'passed', 'testCategory', 'created', 'modified', 'isError', 'score', 'maxScore', 'results')
    POST_permissions_fields = ('submission',)
    read_only_fields = ('testCategory', 'modified', 'created', )
