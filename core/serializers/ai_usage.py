# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import AIUsageRecord, Organization


class AIUsageRecordSerializer(serializers.ModelSerializer):
  """Serializer for individual AI usage records."""
  organizationId = serializers.PrimaryKeyRelatedField(source='organization', read_only=True)
  courseId = serializers.PrimaryKeyRelatedField(source='course', read_only=True)
  assignmentId = serializers.PrimaryKeyRelatedField(source='assignment', read_only=True)
  userId = serializers.PrimaryKeyRelatedField(source='user', read_only=True)
  requestType = serializers.CharField(source='request_type', read_only=True)
  inputTokens = serializers.IntegerField(source='input_tokens', read_only=True)
  outputTokens = serializers.IntegerField(source='output_tokens', read_only=True)
  totalTokens = serializers.IntegerField(source='total_tokens', read_only=True)
  estimatedCost = serializers.DecimalField(source='estimated_cost', max_digits=10, decimal_places=6, read_only=True)
  errorMessage = serializers.CharField(source='error_message', read_only=True)

  class Meta:
    model = AIUsageRecord
    fields = (
      'id',
      'organizationId',
      'courseId',
      'assignmentId',
      'userId',
      'provider',
      'model',
      'requestType',
      'inputTokens',
      'outputTokens',
      'totalTokens',
      'estimatedCost',
      'status',
      'errorMessage',
      'created',
    )


class AIUsageBucketSerializer(serializers.Serializer):
  """A single time bucket in usage aggregation."""
  period = serializers.DateTimeField(help_text="Start of the time bucket")
  totalTokens = serializers.IntegerField(help_text="Total tokens used in this bucket")
  inputTokens = serializers.IntegerField(help_text="Total input tokens in this bucket")
  outputTokens = serializers.IntegerField(help_text="Total output tokens in this bucket")
  estimatedCost = serializers.DecimalField(max_digits=12, decimal_places=6, help_text="Total estimated cost in USD")
  requestCount = serializers.IntegerField(help_text="Number of API calls in this bucket")


class AIUsageBreakdownSerializer(serializers.Serializer):
  """Usage breakdown by a dimension (course, assignment, provider, model)."""
  id = serializers.IntegerField(allow_null=True, help_text="ID of the entity (course or assignment)")
  name = serializers.CharField(help_text="Name/label for this breakdown item")
  totalTokens = serializers.IntegerField()
  inputTokens = serializers.IntegerField()
  outputTokens = serializers.IntegerField()
  estimatedCost = serializers.DecimalField(max_digits=12, decimal_places=6)
  requestCount = serializers.IntegerField()


class AIUsageSummarySerializer(serializers.Serializer):
  """Aggregated usage summary with time-series data and breakdowns."""
  totalTokens = serializers.IntegerField(help_text="Grand total tokens in the range")
  inputTokens = serializers.IntegerField(help_text="Grand total input tokens")
  outputTokens = serializers.IntegerField(help_text="Grand total output tokens")
  estimatedCost = serializers.DecimalField(max_digits=12, decimal_places=6)
  requestCount = serializers.IntegerField(help_text="Total number of requests")
  timeSeries = AIUsageBucketSerializer(many=True, help_text="Usage data bucketed by time")
  breakdown = AIUsageBreakdownSerializer(many=True, help_text="Usage breakdown by dimension")
  granularity = serializers.ChoiceField(choices=['hourly', 'daily', 'monthly'])
  startDate = serializers.DateTimeField()
  endDate = serializers.DateTimeField()


class OrganizationAISettingsSerializer(serializers.ModelSerializer):
  """Serializer for organization-level AI configuration."""
  aiProvider = serializers.ChoiceField(
    source='ai_provider', choices=Organization.AI_PROVIDER_CHOICES,
    required=False, allow_null=True
  )
  aiApiKey = serializers.CharField(
    source='ai_api_key', required=False, allow_null=True,
    allow_blank=True, write_only=True
  )
  aiBaseUrl = serializers.CharField(
    source='ai_base_url', required=False, allow_null=True, allow_blank=True
  )
  aiModel = serializers.CharField(
    source='ai_model', required=False, allow_null=True, allow_blank=True
  )
  aiDisabled = serializers.BooleanField(source='ai_disabled', required=False)
  aiCommentsDisabled = serializers.BooleanField(source='ai_comments_disabled', required=False)
  aiCoursePolicy = serializers.ChoiceField(
    source='ai_course_policy', choices=Organization.AI_COURSE_POLICY_CHOICES,
    required=False
  )
  aiEnabledCourseIds = serializers.PrimaryKeyRelatedField(
    source='ai_enabled_courses', many=True, read_only=True
  )
  aiEnabled = serializers.SerializerMethodField()
  aiCommentsEnabled = serializers.SerializerMethodField()

  class Meta:
    model = Organization
    fields = (
      'id',
      'aiProvider',
      'aiApiKey',
      'aiBaseUrl',
      'aiModel',
      'aiDisabled',
      'aiCommentsDisabled',
      'aiCoursePolicy',
      'aiEnabledCourseIds',
      'aiEnabled',
      'aiCommentsEnabled',
    )

  @extend_schema_field(serializers.BooleanField)
  def get_aiEnabled(self, obj):
    """Returns True if AI is configured and enabled for this organization."""
    return bool(obj.ai_provider and obj.ai_api_key and not obj.ai_disabled)

  @extend_schema_field(serializers.BooleanField)
  def get_aiCommentsEnabled(self, obj):
    """Returns True if AI comments are available at the org level."""
    return bool(obj.ai_provider and obj.ai_api_key and not obj.ai_disabled and not obj.ai_comments_disabled)


class OrganizationAISettingsUpdateSerializer(serializers.ModelSerializer):
  """Serializer for updating organization AI settings including enabled courses."""
  aiProvider = serializers.ChoiceField(
    source='ai_provider', choices=Organization.AI_PROVIDER_CHOICES,
    required=False, allow_null=True
  )
  aiApiKey = serializers.CharField(
    source='ai_api_key', required=False, allow_null=True,
    allow_blank=True, write_only=True
  )
  aiBaseUrl = serializers.CharField(
    source='ai_base_url', required=False, allow_null=True, allow_blank=True
  )
  aiModel = serializers.CharField(
    source='ai_model', required=False, allow_null=True, allow_blank=True
  )
  aiDisabled = serializers.BooleanField(source='ai_disabled', required=False)
  aiCommentsDisabled = serializers.BooleanField(source='ai_comments_disabled', required=False)
  aiCoursePolicy = serializers.ChoiceField(
    source='ai_course_policy', choices=Organization.AI_COURSE_POLICY_CHOICES,
    required=False
  )
  aiEnabledCourseIds = serializers.ListField(
    child=serializers.IntegerField(), required=False, write_only=True,
    help_text="List of course IDs to enable for org AI (used when aiCoursePolicy is 'selected')"
  )

  class Meta:
    model = Organization
    fields = (
      'aiProvider',
      'aiApiKey',
      'aiBaseUrl',
      'aiModel',
      'aiDisabled',
      'aiCommentsDisabled',
      'aiCoursePolicy',
      'aiEnabledCourseIds',
    )

  def update(self, instance, validated_data):
    course_ids = validated_data.pop('aiEnabledCourseIds', None)
    instance = super().update(instance, validated_data)
    if course_ids is not None:
      from core.models import Course
      courses = Course.objects.filter(id__in=course_ids, organization=instance)
      instance.ai_enabled_courses.set(courses)
    return instance
