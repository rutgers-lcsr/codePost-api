from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import SolutionFile


class SolutionFileSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = SolutionFile
    fields = ('id', 'name', 'code', 'name', 'path', 'environment', 'created',)
    POST_permissions_fields = ('environment', )
    extra_kwargs = {"code": {"trim_whitespace": False}}
