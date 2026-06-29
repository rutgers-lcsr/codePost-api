# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import QuestionBank


class QuestionBankSerializer(ModelSerializerWithPOSTCheck):
  questionCount = serializers.IntegerField(source='questions.count', read_only=True)

  class Meta:
    model = QuestionBank
    fields = ('id', 'course', 'name', 'description', 'assignments', 'source', 'createdBy', 'questionCount')
    read_only_fields = ('source', 'createdBy')
    POST_permissions_fields = ('course',)

  def create(self, validated_data):
    request = self.context.get('request')
    if request is not None and validated_data.get('createdBy') is None:
      validated_data['createdBy'] = request.user
    return super().create(validated_data)
