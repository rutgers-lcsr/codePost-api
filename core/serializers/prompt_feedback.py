# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.models import PromptFeedback


class PromptFeedbackSerializer(serializers.ModelSerializer):
    """Serializer for creating and reading PromptFeedback records."""
    promptType = serializers.CharField(source='prompt_type')
    feedbackText = serializers.CharField(source='feedback_text', required=False, allow_blank=True)
    aiOutputA = serializers.CharField(source='ai_output_a', required=False, allow_blank=True)
    aiOutputB = serializers.CharField(source='ai_output_b', required=False, allow_blank=True)
    isCustomContext = serializers.BooleanField(source='is_custom_context', required=False, default=False)
    contextHash = serializers.CharField(source='context_hash', required=False, allow_blank=True)
    variantUsed = serializers.PrimaryKeyRelatedField(source='variant_used', queryset=PromptFeedback.objects.none(), required=False, allow_null=True)
    chosenVariant = serializers.PrimaryKeyRelatedField(source='chosen_variant', queryset=PromptFeedback.objects.none(), required=False, allow_null=True)
    usageRecord = serializers.PrimaryKeyRelatedField(source='usage_record', queryset=PromptFeedback.objects.none(), required=False, allow_null=True)
    experiment = serializers.PrimaryKeyRelatedField(queryset=PromptFeedback.objects.none(), required=False, allow_null=True)

    class Meta:
        model = PromptFeedback
        fields = (
            'id', 'experiment', 'variantUsed', 'chosenVariant', 'user',
            'rating', 'feedbackText', 'aiOutputA', 'aiOutputB',
            'usageRecord', 'promptType', 'isCustomContext', 'contextHash',
            'created', 'modified',
        )
        read_only_fields = ('id', 'user', 'created', 'modified')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import SystemPromptVariant, AIUsageRecord, PromptExperiment
        self.fields['variantUsed'].queryset = SystemPromptVariant.objects.all()
        self.fields['chosenVariant'].queryset = SystemPromptVariant.objects.all()
        self.fields['usageRecord'].queryset = AIUsageRecord.objects.all()
        self.fields['experiment'].queryset = PromptExperiment.objects.all()

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

    def validate_rating(self, value):
        if value is not None and value not in (1, -1):
            raise serializers.ValidationError("Rating must be 1 (thumbs up) or -1 (thumbs down).")
        return value
