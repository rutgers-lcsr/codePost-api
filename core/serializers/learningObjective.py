# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import LearningObjective


class LearningObjectiveSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = LearningObjective
    fields = ('id', 'assignment', 'shortId', 'name', 'description', 'visibilityMode', 'aggregationMode', 'testCases')
    POST_permissions_fields = ('assignment',)
    read_only_fields = ('testCases',)
