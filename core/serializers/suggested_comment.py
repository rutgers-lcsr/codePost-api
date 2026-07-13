# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import SuggestedComment


class SuggestedCommentSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = SuggestedComment
    fields = (
        'id', 'submission', 'file', 'text', 'startLine', 'endLine',
        'startChar', 'endChar', 'rubricComment', 'pointDelta', 'status',
        'acceptedBy', 'acceptedComment', 'generationMetadata',
        'promptVariant', 'generationBatch', 'firstViewedAt',
        'created', 'modified',
    )
    read_only_fields = (
        'id', 'submission', 'file', 'text', 'startLine', 'endLine',
        'startChar', 'endChar', 'rubricComment', 'pointDelta',
        'acceptedBy', 'acceptedComment', 'generationMetadata',
        'promptVariant', 'generationBatch', 'firstViewedAt',
        'created', 'modified',
    )
