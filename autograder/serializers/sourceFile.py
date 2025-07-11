from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import SourceFile


class SourceFileSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = SourceFile
    fields = ('id', 'code', 'name', 'environment',)
    POST_permissions_fields = ('environment', )
    extra_kwargs = {"code": {"trim_whitespace": False}}
