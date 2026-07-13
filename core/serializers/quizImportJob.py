# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.models import QuizImportJob


class QuizImportJobSerializer(serializers.ModelSerializer):
  """Read-only view of a QTI / Common Cartridge import job (for status polling)."""

  class Meta:
    model = QuizImportJob
    fields = (
        'id', 'course', 'status', 'taskId', 'targetBank',
        'createdQuizCount', 'createdQuestionCount', 'errorMessage', 'summary', 'created',
    )
    read_only_fields = fields
