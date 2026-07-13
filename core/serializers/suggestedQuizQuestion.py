# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import SuggestedQuizQuestion


class SuggestedQuizQuestionSerializer(ModelSerializerWithPOSTCheck):
  """An AI quiz-question suggestion. Staff-only. A pending suggestion's content may be
  edited (PATCH) before it is accepted into a real Question. ``status`` and the link
  fields are system-managed via the accept/reject actions."""

  # The model's jsonfield.JSONField would otherwise serialize as a Python-repr string;
  # declare it explicitly so the proposed choices are emitted as real JSON.
  choicesData = serializers.JSONField(required=False)

  class Meta:
    model = SuggestedQuizQuestion
    fields = (
        'id', 'assignment', 'sourceQuestion', 'questionType', 'text', 'choicesData',
        'points', 'language', 'starterCode', 'referenceSolution', 'status',
        'acceptedBy', 'acceptedQuestion', 'generationBatch', 'created',
    )
    read_only_fields = (
        'assignment', 'sourceQuestion', 'status', 'acceptedBy', 'acceptedQuestion',
        'generationBatch', 'created',
    )
