# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import SubmissionSummary


class SubmissionSummarySerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = SubmissionSummary
    fields = ('id', 'submission', 'text', 'generationMetadata', 'regenerationCount', 'created', 'modified')
    read_only_fields = ('id', 'submission', 'text', 'generationMetadata', 'regenerationCount', 'created', 'modified')
