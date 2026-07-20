# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers

from core.models import SubmissionVariantRun


class SubmissionVariantRunSerializer(serializers.ModelSerializer):
    """One variant-robustness rerun. Staff-only — never exposed to students."""

    datasetName = serializers.CharField(source='dataset.name', read_only=True)

    class Meta:
        model = SubmissionVariantRun
        fields = ('id', 'submission', 'dataset', 'datasetName', 'result', 'created', 'modified')
        read_only_fields = fields
