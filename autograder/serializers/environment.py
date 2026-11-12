# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Environment
from autograder.services import environment_packages

# detected: from the instructor's files and tests. learned: enough student runs needed it.
# pinned: an instructor added it.
PACKAGE_ORIGIN_CHOICES = [('detected', 'Detected'), ('learned', 'Learned'), ('pinned', 'Pinned')]
# counting: not enough submissions yet. not_found: not on the package index.
# build_failed: it was learned, broke the build, and was dropped.
PENDING_PACKAGE_STATUS_CHOICES = [('counting', 'Counting'), ('not_found', 'Not Found'), ('build_failed', 'Build Failed')]


class EnvironmentPackageSerializer(serializers.Serializer):
  name = serializers.CharField()
  requirement = serializers.CharField(help_text="The requirement line, e.g. numpy==1.26.4")
  origin = serializers.ChoiceField(choices=PACKAGE_ORIGIN_CHOICES)


class EnvironmentPendingPackageSerializer(serializers.Serializer):
  name = serializers.CharField()
  count = serializers.IntegerField(help_text="Distinct submissions whose run needed the package")
  status = serializers.ChoiceField(choices=PENDING_PACKAGE_STATUS_CHOICES)


class EnvironmentSerializer(ModelSerializerWithPOSTCheck):
  dockerRunInstructions = serializers.JSONField(default=[])  # type: ignore[arg-type]  # DRF accepts list as default
  
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
  
  # Package lists behind `requirements` (python and r; see services/environment_packages.py)
  packageListSupported = serializers.SerializerMethodField()
  packages = serializers.SerializerMethodField()
  excludedPackages = serializers.ListField(source='excluded_packages', child=serializers.CharField(), read_only=True)
  pendingPackages = serializers.SerializerMethodField()
  imageOutOfDate = serializers.SerializerMethodField()
  rebuildScheduled = serializers.SerializerMethodField()

  @extend_schema_field(serializers.BooleanField)
  def get_packageListSupported(self, obj):
    return environment_packages.supports_package_list(obj.language)

  @extend_schema_field(EnvironmentPackageSerializer(many=True))
  def get_packages(self, obj):
    return environment_packages.describe_packages(obj)

  @extend_schema_field(EnvironmentPendingPackageSerializer(many=True))
  def get_pendingPackages(self, obj):
    return environment_packages.pending_packages(obj)

  @extend_schema_field(serializers.BooleanField)
  def get_imageOutOfDate(self, obj):
    return environment_packages.image_out_of_date(obj)

  @extend_schema_field(serializers.BooleanField)
  def get_rebuildScheduled(self, obj):
    return obj.rebuild_scheduled_at is not None

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
              'successfulRuns', 'totalRuns', 'successRate',
              'packageListSupported', 'packages', 'excludedPackages', 'pendingPackages',
              'imageOutOfDate', 'rebuildScheduled')

    POST_permissions_fields = ('assignment', )
    read_only_fields = ()
    extra_kwargs = {"compileText": {"trim_whitespace": False}}

