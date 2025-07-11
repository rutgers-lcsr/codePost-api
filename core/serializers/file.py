from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import File
from django import forms


class FileSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = File
    fields = ('name', 'code', 'extension', 'submission', 'id', 'comments', 'path', 'created')
    read_only_fields = ('comments', )
    POST_permissions_fields = ('submission',)
    extra_kwargs = {"code": {"trim_whitespace": False}}


class FileStudentUploadSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = File
    fields = ('name', 'code', 'extension', 'submission', 'id', 'path')
    POST_permissions_fields = ('submission',)
    extra_kwargs = {"code": {"trim_whitespace": False}}


class FileValidationSerializerWithoutSubmission(serializers.Serializer):
  """
  Validate data without creating a submission
  """
  name = serializers.CharField(max_length=150, required=True)
  code = serializers.CharField(required=True, trim_whitespace=False)
  extension = serializers.CharField(max_length=36, required=True)
  path = serializers.CharField(max_length=500, allow_null=True, allow_blank=True, required=False)
