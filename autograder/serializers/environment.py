from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Environment


class EnvironmentSerializer(ModelSerializerWithPOSTCheck):
  dockerRunInstructions = serializers.JSONField(default=[])
  
  # Map snake_case model fields to camelCase API fields
  autoDetect = serializers.BooleanField(source='auto_detect', required=False)
  imageName = serializers.CharField(source='image_name', required=False, allow_null=True, allow_blank=True)
  buildStatus = serializers.IntegerField(source='build_status', read_only=True)
  buildLogs = serializers.CharField(source='build_logs', read_only=True)
  lastBuilt = serializers.DateTimeField(source='last_built', read_only=True)

  requirements = serializers.CharField(required=False, allow_blank=True)
  envVars = serializers.JSONField(source='env_vars', required=False)
  
  # Convergence and version tracking (read-only for display)
  currentBuildVersion = serializers.IntegerField(source='current_build_version', read_only=True)
  imageHistory = serializers.JSONField(source='image_history', read_only=True)
  convergencePending = serializers.BooleanField(source='convergence_pending', read_only=True)
  convergenceStats = serializers.JSONField(source='convergence_stats', read_only=True)
  successfulRuns = serializers.IntegerField(source='successful_runs', read_only=True)
  totalRuns = serializers.IntegerField(source='total_runs', read_only=True)
  
  # Computed field for success rate
  successRate = serializers.SerializerMethodField()
  
  @extend_schema_field(serializers.FloatField)
  def get_successRate(self, obj):
    if obj.total_runs > 0:
      return round((obj.successful_runs / obj.total_runs) * 100, 1)
    return 0

  class Meta:
    model = Environment
    fields = ('id', 'assignment', 'language', 'dockerRunInstructions', 'compileText',
              'dockerfile', 'buildType', 'allowNetworkAccess', 'maxStudentTestRuns', 'maxExposedFailedTests', 
              'autoDetect', 'imageName', 'buildStatus', 'buildLogs', 'lastBuilt', 'requirements', 'envVars',
              'currentBuildVersion', 'imageHistory', 'convergencePending', 'convergenceStats',
              'successfulRuns', 'totalRuns', 'successRate')

    POST_permissions_fields = ('assignment', )
    read_only_fields = ()
    extra_kwargs = {"compileText": {"trim_whitespace": False}}

