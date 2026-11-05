# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.models import SystemPromptVariant
from core.prompts.validation import validate_prompt_placeholders


class SystemPromptVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemPromptVariant
        fields = (
            'id', 'promptType', 'name', 'text', 'status', 'version',
            'parent', 'createdBy', 'metadata', 'created', 'modified',
        )
        read_only_fields = ('id', 'version', 'createdBy', 'created', 'modified')

    # camelCase field name mapping (djangorestframework-camel-case handles serialization,
    # but we need explicit source mapping for the model's snake_case fields).
    promptType = serializers.CharField(source='prompt_type')
    createdBy = serializers.PrimaryKeyRelatedField(source='created_by', read_only=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        prompt_type = attrs['prompt_type'] if 'prompt_type' in attrs else (
            self.instance.prompt_type if self.instance else None)
        text = attrs['text'] if 'text' in attrs else (self.instance.text if self.instance else '')

        if prompt_type:
            validate_prompt_placeholders(text, prompt_type)

        return attrs

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class SystemPromptVariantSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for embedding inside experiment responses."""
    class Meta:
        model = SystemPromptVariant
        fields = ('id', 'promptType', 'name', 'status', 'version')

    promptType = serializers.CharField(source='prompt_type', read_only=True)
