# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.prompts.registry import (
    describe_prompt_placeholders,
    describe_prompt_templates,
    prompt_registry,
)


class PromptTypeListView(APIView):
    """Return the list of registered prompt types and their insertable {placeholders}.

    Available to any authenticated user — the Prompt Lab UI and the instructor-facing
    assignment prompt editors both need this descriptive metadata to power their variable
    dropdowns. It exposes only names/labels/descriptions, never prompt text; editing
    variants stays superuser-only (PromptExperimentViewSet).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='promptTypes_list',
        description='List all registered AI prompt types with their insertable {placeholders}.',
        responses={200: inline_serializer('PromptType', {
            'key': serializers.CharField(),
            'label': serializers.CharField(),
            'description': serializers.CharField(),
            'placeholders': inline_serializer('PromptVariable', {
                'token': serializers.CharField(),
                'name': serializers.CharField(),
                'argument': serializers.CharField(allow_null=True),
                'label': serializers.CharField(),
                'description': serializers.CharField(),
                'kind': serializers.CharField(),
            }, many=True),
            'templates': inline_serializer('PromptTemplate', {
                'key': serializers.CharField(),
                'label': serializers.CharField(),
                'description': serializers.CharField(),
                'text': serializers.CharField(),
            }, many=True),
        }, many=True)},
    )
    def get(self, request):
        data = [
            {
                'key': entry.key,
                'label': entry.label,
                'description': entry.description,
                'placeholders': describe_prompt_placeholders(entry.key),
                'templates': describe_prompt_templates(entry.key),
            }
            for entry in prompt_registry.all()
        ]
        return Response(data)
