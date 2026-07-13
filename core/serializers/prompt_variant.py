# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import string

from rest_framework import serializers
from core.models import SystemPromptVariant
from core.prompts.registry import prompt_registry


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
        prompt_type = attrs.get('prompt_type') or (self.instance.prompt_type if self.instance else None)
        text = attrs.get('text') or (self.instance.text if self.instance else '')

        if prompt_type and text:
            allowed = prompt_registry.get_allowed_placeholders(prompt_type)
            if allowed:
                # Extract placeholder names from the template using string.Formatter
                formatter = string.Formatter()
                used = set()
                try:
                    for _, field_name, _, _ in formatter.parse(text):
                        if field_name is not None:
                            # Handle nested access like {foo.bar} — only validate the root name
                            root = field_name.split('.')[0].split('[')[0]
                            if root:
                                used.add(root)
                except (ValueError, KeyError):
                    raise serializers.ValidationError({
                        'text': 'Invalid template syntax. Check for unmatched or malformed {placeholders}.'
                    })

                invalid = used - allowed
                if invalid:
                    sorted_invalid = ', '.join(sorted(invalid))
                    sorted_allowed = ', '.join(sorted(allowed))
                    raise serializers.ValidationError({
                        'text': (
                            f'Unknown placeholder(s): {{{sorted_invalid}}}. '
                            f'Allowed placeholders for {prompt_type}: {{{sorted_allowed}}}.'
                        )
                    })

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
