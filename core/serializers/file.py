from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import File, SubmissionFile, AssignmentFile, CourseFile
from django import forms


class FileSerializer(ModelSerializerWithPOSTCheck):
    """
    Base serializer for File objects.
    Note: 'data' field was previously called 'code' - both are supported for backwards compatibility.
    """
    # Support both 'data' (new) and 'code' (legacy) field names
    code = serializers.CharField(source='data', trim_whitespace=False, required=False, allow_blank=True)

    class Meta:
        model = File
        fields = ('name', 'data', 'code', 'extension', 'id', 'path', 'created', 'modified')
        read_only_fields = ('created', 'modified')
        extra_kwargs = {
            "data": {"trim_whitespace": False},
            "code": {"trim_whitespace": False}
        }


class SubmissionFileSerializer(ModelSerializerWithPOSTCheck):
    """
    Serializer for SubmissionFile objects.
    These are files that belong to student submissions.
    """
    # Support both 'data' (new) and 'code' (legacy) field names
    code = serializers.CharField(source='data', trim_whitespace=False, required=False, allow_blank=True)

    class Meta:
        model = SubmissionFile
        fields = ('name', 'data', 'code', 'extension', 'submission', 'id', 'comments', 'path', 
                  'hiddenBeforePublish', 'created', 'modified')
        read_only_fields = ('comments', 'created', 'modified')
        POST_permissions_fields = ('submission',)
        extra_kwargs = {
            "data": {"trim_whitespace": False},
            "code": {"trim_whitespace": False}
        }


class SubmissionFileWithoutCommentsSerializer(ModelSerializerWithPOSTCheck):
    """
    Serializer for SubmissionFile objects without comments field.
    Used for files-only view where students can see files but not comments.
    """
    # Support both 'data' (new) and 'code' (legacy) field names
    code = serializers.CharField(source='data', trim_whitespace=False, required=False, allow_blank=True)

    class Meta:
        model = SubmissionFile
        fields = ('name', 'data', 'code', 'extension', 'submission', 'id', 'path', 
                  'hiddenBeforePublish', 'created', 'modified')
        read_only_fields = ('created', 'modified')
        POST_permissions_fields = ('submission',)
        extra_kwargs = {
            "data": {"trim_whitespace": False},
            "code": {"trim_whitespace": False}
        }


class SubmissionFileStudentUploadSerializer(ModelSerializerWithPOSTCheck):
    """
    Simplified serializer for students uploading submission files.
    """
    # Support both 'data' (new) and 'code' (legacy) field names
    code = serializers.CharField(source='data', trim_whitespace=False, required=False, allow_blank=True)

    class Meta:
        model = SubmissionFile
        fields = ('name', 'data', 'code', 'extension', 'submission', 'id', 'path')
        POST_permissions_fields = ('submission',)
        extra_kwargs = {
            "data": {"trim_whitespace": False},
            "code": {"trim_whitespace": False}
        }


class AssignmentFileSerializer(ModelSerializerWithPOSTCheck):
    """
    Serializer for AssignmentFile objects.
    These are files that belong to assignments (templates, instructions, etc.).
    """
    # Support both 'data' (new) and 'code' (legacy) field names
    code = serializers.CharField(source='data', trim_whitespace=False, required=False, allow_blank=True)

    class Meta:
        model = AssignmentFile
        fields = ('name', 'data', 'code', 'extension', 'assignment', 'id', 'path', 'required', 'description', 'created', 'modified')
        read_only_fields = ('created', 'modified')
        POST_permissions_fields = ('assignment',)
        extra_kwargs = {
            "data": {"trim_whitespace": False},
            "code": {"trim_whitespace": False}
        }


class CourseFileSerializer(ModelSerializerWithPOSTCheck):
    """
    Serializer for CourseFile objects.
    These are files that belong to courses (syllabi, resources, etc.).
    """
    # Support both 'data' (new) and 'code' (legacy) field names
    code = serializers.CharField(source='data', trim_whitespace=False, required=False, allow_blank=True)

    class Meta:
        model = CourseFile
        fields = ('name', 'data', 'code', 'extension', 'course', 'id', 'path', 'created', 'modified')
        read_only_fields = ('created', 'modified')
        POST_permissions_fields = ('course',)
        extra_kwargs = {
            "data": {"trim_whitespace": False},
            "code": {"trim_whitespace": False}
        }


class FileValidationSerializerWithoutSubmission(serializers.Serializer):
    """
    Validate file data without creating a submission.
    Supports both 'data' and 'code' field names for backwards compatibility.
    """
    name = serializers.CharField(max_length=250, required=True)
    data = serializers.CharField(required=False, trim_whitespace=False, allow_blank=True)
    code = serializers.CharField(required=False, trim_whitespace=False, allow_blank=True)
    extension = serializers.CharField(max_length=36, required=True)
    path = serializers.CharField(max_length=500, allow_null=True, allow_blank=True, required=False)

    def validate(self, attrs):
        # Ensure either 'data' or 'code' is provided
        if not attrs.get('data') and not attrs.get('code'):
            raise serializers.ValidationError("Either 'data' or 'code' field must be provided")
        
        # If 'code' is provided but not 'data', copy it over
        if attrs.get('code') and not attrs.get('data'):
            attrs['data'] = attrs['code']
        
        return attrs
