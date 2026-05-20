# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import SubmissionTest


class HiddenTestSummarySerializer(serializers.Serializer):
  """
  Replaces individual hidden-test rows in student-facing responses. The student learns
  how many hidden tests they passed and the point impact, but never sees the underlying
  TestCase names, descriptions, or logs.
  """
  label = serializers.CharField()
  passedCount = serializers.IntegerField()
  totalCount = serializers.IntegerField()
  pointsEarned = serializers.FloatField()
  pointsTotal = serializers.FloatField()


class SubmissionTestSerializer(ModelSerializerWithPOSTCheck):
  testCategory = serializers.ReadOnlyField(source='testCase.testCategory.id')
  hiddenSummary = serializers.SerializerMethodField(allow_null=True)

  class Meta:
    model = SubmissionTest
    fields = ('id', 'submission', 'testCase', 'logs', 'passed', 'testCategory', 'created', 'modified',
              'isError', 'score', 'maxScore', 'results', 'hiddenSummary')
    POST_permissions_fields = ('submission',)
    read_only_fields = ('testCategory', 'modified', 'created', 'hiddenSummary')

  @extend_schema_field(HiddenTestSummarySerializer(allow_null=True))
  def get_hiddenSummary(self, obj):
    # Real SubmissionTest instances always serialize as null. The submissionTestResults
    # action constructs synthetic per-category rows (plain dicts) with hiddenSummary
    # populated to replace individual hidden-test rows for student viewers.
    return None
