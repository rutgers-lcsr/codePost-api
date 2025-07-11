from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import FileTemplate
from django import forms


class FileTemplateSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = FileTemplate
    fields = ('name', 'code', 'extension', 'id', 'path', 'assignment', 'required', 'description')
    extra_kwargs = {"code": {"trim_whitespace": False}}
