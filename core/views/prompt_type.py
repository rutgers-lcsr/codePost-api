# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.prompts.registry import prompt_registry


class PromptTypeListView(APIView):
    """Return the list of registered prompt types.

    Available to any authenticated user (the PromptLab UI needs the list),
    but only superusers can create/edit variants via PromptExperimentViewSet.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        operation_id='promptTypes_list',
        description='List all registered AI prompt types.',
        responses={200: {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'key': {'type': 'string'},
                    'label': {'type': 'string'},
                    'description': {'type': 'string'},
                },
            },
        }},
    )
    def get(self, request):
        data = [
            {
                'key': entry.key,
                'label': entry.label,
                'description': entry.description,
            }
            for entry in prompt_registry.all()
        ]
        return Response(data)
