from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Environment


class EnvironmentSerializer(ModelSerializerWithPOSTCheck):
  dockerRunInstructions = serializers.JSONField(default=[])

  class Meta:
    model = Environment
    fields = ('id', 'assignment', 'language', 'dockerRunInstructions', 'helperFiles', 'solutionFiles', 'compileText', 'isRunning', 'sourceFiles', 'dumpMode',
              'testParsing', 'dockerfile', 'buildType', 'allowNetworkAccess', 'maxStudentTestRuns', 'exposeDumpLogs', 'maxExposedFailedTests', )

    POST_permissions_fields = ('assignment', )
    read_only_fields = ('helperFiles',  'solutionFiles', 'isRunning', 'sourceFiles')
    extra_kwargs = {"compileText": {"trim_whitespace": False}}
