# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import TestCategoryResource
from core.serializers.file import AssignmentFileSerializer
from core.serializers.assignmentDataSet import AssignmentDataSetSerializer

class TestCategoryResourceSerializer(ModelSerializerWithPOSTCheck):
    __test__ = False

    targetPath = serializers.CharField(source='target_path')
    # Nested read-only fields for detailed display
    fileDetails = AssignmentFileSerializer(source='file', read_only=True)
    datasetDetails = AssignmentDataSetSerializer(source='dataset', read_only=True)

    class Meta:
        model = TestCategoryResource
        fields = ('id', 'category', 'file', 'dataset', 'targetPath', 'fileDetails', 'datasetDetails')
    POST_permissions_fields = ('category',)
