# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.models import QuizSuggestionJob


class QuizSuggestionJobSerializer(serializers.ModelSerializer):
  """Read-only view of an AI quiz-suggestion generation run (for status polling)."""

  # Explicit JSONField so the generated TS client types it `any` (the auto-mapped
  # jsonfield.JSONField would come out as `string`, like QuizImportJob.summary).
  resultData = serializers.JSONField(read_only=True)

  class Meta:
    model = QuizSuggestionJob
    fields = (
        'id', 'course', 'assignment', 'sourceQuestion', 'quiz', 'status', 'taskId',
        'createdCount', 'errorMessage', 'resultData', 'created',
    )
    read_only_fields = fields
