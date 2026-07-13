# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.models import PromptExperiment
from core.serializers.prompt_variant import SystemPromptVariantSummarySerializer


class PromptExperimentSerializer(serializers.ModelSerializer):
    variantA = serializers.PrimaryKeyRelatedField(source='variant_a', queryset=PromptExperiment.objects.none())
    variantB = serializers.PrimaryKeyRelatedField(source='variant_b', queryset=PromptExperiment.objects.none())
    variantADetail = SystemPromptVariantSummarySerializer(source='variant_a', read_only=True)
    variantBDetail = SystemPromptVariantSummarySerializer(source='variant_b', read_only=True)
    promptType = serializers.CharField(source='prompt_type')
    startedBy = serializers.PrimaryKeyRelatedField(source='started_by', read_only=True)
    completedAt = serializers.DateTimeField(source='completed_at', read_only=True)
    sampleRate = serializers.FloatField(source='sample_rate')

    class Meta:
        model = PromptExperiment
        fields = (
            'id', 'name', 'promptType', 'variantA', 'variantB',
            'variantADetail', 'variantBDetail',
            'status', 'sampleRate', 'startedBy', 'completedAt',
            'created', 'modified',
        )
        read_only_fields = ('id', 'startedBy', 'completedAt', 'created', 'modified')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import SystemPromptVariant
        variant_qs = SystemPromptVariant.objects.all()
        self.fields['variantA'].queryset = variant_qs
        self.fields['variantB'].queryset = variant_qs

    def create(self, validated_data):
        validated_data['started_by'] = self.context['request'].user
        return super().create(validated_data)

    def validate_sampleRate(self, value):
        if not 0.0 <= value <= 1.0:
            raise serializers.ValidationError("Sample rate must be between 0.0 and 1.0.")
        return value


class VariantBehavioralStatsSerializer(serializers.Serializer):
    """Behavioral stats for a single variant."""
    total = serializers.IntegerField()
    accepted = serializers.IntegerField()
    rejected = serializers.IntegerField()
    pending = serializers.IntegerField()
    acceptanceRate = serializers.FloatField(allow_null=True)
    rejectionRate = serializers.FloatField(allow_null=True)
    editRate = serializers.FloatField(allow_null=True)
    avgTimeToDecideSeconds = serializers.FloatField(allow_null=True)
    distinctAssignments = serializers.IntegerField()


class BehavioralMetricsSerializer(serializers.Serializer):
    """Behavioral metrics comparing both variants."""
    variantA = VariantBehavioralStatsSerializer()
    variantB = VariantBehavioralStatsSerializer()
    variantAConfident = serializers.BooleanField()
    variantBConfident = serializers.BooleanField()
    batchAcceptanceRateA = serializers.FloatField(allow_null=True)
    batchAcceptanceRateB = serializers.FloatField(allow_null=True)
    minAssignmentsThreshold = serializers.IntegerField()
    minSamplesThreshold = serializers.IntegerField()


class PromptExperimentResultsSerializer(serializers.Serializer):
    """Aggregated results for a completed (or running) experiment."""
    experimentId = serializers.IntegerField()
    promptType = serializers.CharField()
    totalFeedback = serializers.IntegerField()
    variantAWins = serializers.IntegerField()
    variantBWins = serializers.IntegerField()
    ties = serializers.IntegerField()
    defaultPoolCount = serializers.IntegerField()
    customPoolCount = serializers.IntegerField()
    thumbsUp = serializers.IntegerField()
    thumbsDown = serializers.IntegerField()
    behavioral = BehavioralMetricsSerializer()
