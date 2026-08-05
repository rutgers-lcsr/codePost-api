# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.models import QuizSuggestionJob


class QuizSuggestionJobSerializer(serializers.ModelSerializer):
  """Read-only view of an AI quiz-suggestion generation run (for status polling)."""

  class Meta:
    model = QuizSuggestionJob
    fields = (
        'id', 'course', 'assignment', 'sourceQuestion', 'status', 'taskId',
        'createdCount', 'errorMessage', 'created',
    )
    read_only_fields = fields
