from rest_framework import serializers
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
