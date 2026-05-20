# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import File, SubmissionFile, AssignmentFile, CourseFile, SubmissionFileEdit
from core.services.file_handlers.notebook import NotebookHandler
from core.serializers.comment import CommentWithRubricSerializer


class SubmissionFileEditSerializer(serializers.ModelSerializer):
    lastEditedBy = serializers.SlugRelatedField(read_only=True, slug_field='email')

    class Meta:
        model = SubmissionFileEdit
        fields = ('data', 'lastEditedBy', 'created', 'modified')
        read_only_fields = fields


class SubmissionFileEditSaveSerializer(serializers.Serializer):
    fileId = serializers.IntegerField(required=True)
    data = serializers.CharField(required=True, trim_whitespace=False, allow_blank=True)  # type: ignore[assignment]


class FileSerializer(ModelSerializerWithPOSTCheck):
    """
    Base serializer for File objects.
    """

    class Meta:
        model = File
        fields = ('name', 'data', 'extension', 'id', 'path', 'created', 'modified')
        read_only_fields = ('created', 'modified')
        extra_kwargs = {
            "data": {"trim_whitespace": False},
        }


class SubmissionFileSerializer(ModelSerializerWithPOSTCheck):
    """
    Serializer for SubmissionFile objects.
    These are files that belong to student submissions.
    """
    edit = SubmissionFileEditSerializer(read_only=True)

    class Meta:
        model = SubmissionFile
        fields = ('name', 'data', 'extension', 'submission', 'id', 'comments', 'path',
                  'hiddenBeforePublish', 'created', 'modified', 'edit')
        read_only_fields = ('comments', 'created', 'modified', 'edit')
        POST_permissions_fields = ('submission',)
        extra_kwargs = {
            "data": {"trim_whitespace": False},
        }


class SubmissionFileWithNestedCommentsSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for SubmissionFile that nests full Comment objects
    (including rubricComment data) instead of returning comment IDs.
    Used by the console-data bulk endpoint to eliminate N+1 fetches.
    """
    comments = CommentWithRubricSerializer(many=True, read_only=True)
    edit = SubmissionFileEditSerializer(read_only=True)

    class Meta:
        model = SubmissionFile
        fields = ('name', 'data', 'extension', 'submission', 'id', 'comments', 'path',
                  'hiddenBeforePublish', 'created', 'modified', 'edit')
        read_only_fields = fields


class SubmissionFileWithoutCommentsSerializer(ModelSerializerWithPOSTCheck):
    """
    Serializer for SubmissionFile objects without comments field.
    Used for files-only view where students can see files but not comments.
    """
    edit = serializers.SerializerMethodField()

    class Meta:
        model = SubmissionFile
        fields = ('name', 'data', 'extension', 'submission', 'id', 'path',
                  'hiddenBeforePublish', 'created', 'modified', 'comments', 'edit')
        read_only_fields = ('created', 'modified', 'edit')

    comments = serializers.SerializerMethodField()

    @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
    def get_comments(self, obj):
        return []

    @extend_schema_field(SubmissionFileEditSerializer(allow_null=True))
    def get_edit(self, obj):
        edit = getattr(obj, 'edit', None)
        if edit is None:
            return None
        return SubmissionFileEditSerializer(edit).data


class SubmissionFileStudentUploadSerializer(ModelSerializerWithPOSTCheck):
    """
    Simplified serializer for students uploading submission files.
    """

    class Meta:
        model = SubmissionFile
        fields = ('name', 'data', 'extension', 'submission', 'id', 'path')
        POST_permissions_fields = ('submission',)
        extra_kwargs = {
            "data": {"trim_whitespace": False},
        }


class AssignmentFileSerializer(ModelSerializerWithPOSTCheck):
    """
    Serializer for AssignmentFile objects.
    These are files that belong to assignments (templates, instructions, etc.).
    """

    isTestResource = serializers.BooleanField(source='is_test_resource', required=False)

    class Meta:
        model = AssignmentFile
        fields = ('name', 'data', 'extension', 'assignment', 'id', 'path', 'required', 'description', 'created', 'modified', 'hidden', 'isTestResource')
        read_only_fields = ('created', 'modified')
        POST_permissions_fields = ('assignment',)
        extra_kwargs = {
            "data": {"trim_whitespace": False},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get('extension') == '.ipynb' and attrs.get('data'):
            attrs['data'] = NotebookHandler.inject_cell_ids(attrs['data'])
        return attrs


class AssignmentFileSummarySerializer(ModelSerializerWithPOSTCheck):
    """
    Summary serializer for AssignmentFile objects.
    Excludes 'data' to reduce payload size in list views.
    """

    isTestResource = serializers.BooleanField(source='is_test_resource', required=False)

    class Meta:
        model = AssignmentFile
        fields = ('name', 'extension', 'assignment', 'id', 'path', 'required', 'description', 'created', 'modified', 'hidden', 'isTestResource')
        read_only_fields = ('created', 'modified')
        POST_permissions_fields = ('assignment',)


class AssignmentFilePublicSerializer(serializers.ModelSerializer):
    """
    Public serializer for AssignmentFile objects.
    Used for listing files in the student dashboard (excludes data).
    """

    class Meta:
        model = AssignmentFile
        fields = ('id', 'name', 'extension', 'required', 'description', 'created', 'modified', 'assignment', 'path', 'hidden')
        read_only_fields = fields


class CourseFileSerializer(ModelSerializerWithPOSTCheck):
    """
    Serializer for CourseFile objects.
    These are files that belong to courses (syllabi, resources, etc.).
    """

    class Meta:
        model = CourseFile
        fields = ('name', 'data', 'extension', 'course', 'id', 'path', 'created', 'modified')
        read_only_fields = ('created', 'modified')
        POST_permissions_fields = ('course',)
        extra_kwargs = {
            "data": {"trim_whitespace": False},
        }


class FileValidationSerializerWithoutSubmission(serializers.Serializer):
    """
    Validate file data without creating a submission.
    """
    name = serializers.CharField(max_length=250, required=True)
    data = serializers.CharField(required=True, trim_whitespace=False, allow_blank=True)  # type: ignore[assignment]  # DRF field overrides base property
    extension = serializers.CharField(max_length=36, required=True)
    path = serializers.CharField(max_length=500, allow_null=True, allow_blank=True, required=False)

    def validate(self, attrs):
        return attrs
