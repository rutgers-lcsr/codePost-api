# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import TestCategory

from core.serializers.testCategoryResource import TestCategoryResourceSerializer

class TestCategorySerializer(ModelSerializerWithPOSTCheck):
  resources = TestCategoryResourceSerializer(many=True, read_only=True)

  class Meta:
    model = TestCategory
    fields = ('id', 'name', 'testCases', 'assignment', 'testScript', 'maxPoints', 'sortKey', 'targetFileName', 'resources')
    POST_permissions_fields = ('assignment',)
    read_only_fields = ('testCases', 'testFiles', 'resources')

