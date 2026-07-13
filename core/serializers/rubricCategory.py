# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import RubricCategory

class RubricCategorySerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = RubricCategory
    fields = ('id', 'assignment', 'name', 'pointLimit', 'rubricComments', 'sortKey', 'helpText', 'atMostOnce')
    read_only_fields = ('rubricComments',)
    POST_permissions_fields = ('assignment',)

class RubricCategoryStudentSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = RubricCategory
    fields = ('id', 'assignment', 'name', 'pointLimit', 'rubricComments', 'sortKey', 'atMostOnce')
    read_only_fields = ('rubricComments',)
    POST_permissions_fields = ('assignment',)
