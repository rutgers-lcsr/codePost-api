from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import FileTemplate
from django import forms


class FileTemplateSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = FileTemplate
    fields = ('name', 'data', 'extension', 'id', 'path', 'assignment', 'required', 'description')
    extra_kwargs = {
        "data": {"trim_whitespace": False},
    }
