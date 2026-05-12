# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import TestCase


class TestCaseSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = TestCase
    fields = ('id', 'testCategory', 'sortKey', 'description', 'type', 'pointsFail', 'pointsPass', 'text', 'modified',
              'exposed', 'instances', 'explanation', 'lastSolutionRun', 'testCode', 'targetCellId', 'rubricItem', 'functionName', 'timeout')
    POST_permissions_fields = ('testCategory',)
    read_only_fields = ('modified', 'instances',)
    extra_kwargs = {"text": {"trim_whitespace": False}, "description": {
        "trim_whitespace": False}, "explanation": {"trim_whitespace": False}}


class TestCaseStudentSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = TestCase
    fields = ('id', 'testCategory', 'sortKey', 'description', 'pointsFail', 'pointsPass', 'explanation', 'exposed', 'rubricItem')
    POST_permissions_fields = ('testCategory',)
    extra_kwargs = {"description": {"trim_whitespace": False}, "explanation": {"trim_whitespace": False}}
