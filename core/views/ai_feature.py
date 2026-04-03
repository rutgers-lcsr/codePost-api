# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.ai_features.registry import ai_feature_registry


class AIFeatureListView(APIView):
    """Return the list of registered AI features and their defaults.

    Used by the course and org settings UIs to render dynamic toggle lists.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id='aiFeatures_list',
        description='List all registered AI features with their defaults.',
        responses={200: {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'key': {'type': 'string'},
                    'label': {'type': 'string'},
                    'description': {'type': 'string'},
                    'defaultEnabled': {'type': 'boolean'},
                    'requires': {'type': 'array', 'items': {'type': 'string'}},
                },
            },
        }},
    )
    def get(self, request):
        import core.ai_features  # noqa: F401 — trigger registration
        data = [
            {
                'key': entry.key,
                'label': entry.label,
                'description': entry.description,
                'defaultEnabled': entry.default_enabled,
                'requires': list(entry.requires),
            }
            for entry in ai_feature_registry.all()
        ]
        return Response(data)
