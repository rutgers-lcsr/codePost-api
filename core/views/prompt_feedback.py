# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from core.models import PromptFeedback
from core.serializers.prompt_feedback import PromptFeedbackSerializer
from core.views.template import ListProtectedViewSet, ListPagination

from logging import getLogger
logger = getLogger(__name__)


class PromptFeedbackPermission(BasePermission):
    """
    Any authenticated user can create feedback.
    Only superusers can list/retrieve feedback records.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(view, 'action', None) in ('create',):
            return True
        # list, retrieve, etc. require superuser
        return bool(request.user.is_superuser)  # type: ignore[union-attr]


class PromptFeedbackViewSet(ListProtectedViewSet):
    """
    Prompt feedback from graders/admins on AI-generated output.

    create:
    Submit feedback (any authenticated user).

    list / retrieve:
    Superuser-only. Supports ?promptType=, ?experimentId=, ?isCustomContext= filters.
    """
    queryset = PromptFeedback.objects.select_related(
        'experiment', 'variant_used', 'chosen_variant', 'user',
    ).all()
    serializer_class = PromptFeedbackSerializer
    permission_classes = (PromptFeedbackPermission,)
    pagination_class = ListPagination

    def get_queryset(self):
        qs = super().get_queryset()
        prompt_type = self.request.query_params.get('promptType')
        if prompt_type:
            qs = qs.filter(prompt_type=prompt_type)
        experiment_id = self.request.query_params.get('experimentId')
        if experiment_id:
            try:
                qs = qs.filter(experiment_id=int(experiment_id))
            except (ValueError, TypeError):
                pass
        is_custom = self.request.query_params.get('isCustomContext')
        if is_custom is not None:
            qs = qs.filter(is_custom_context=is_custom.lower() in ('true', '1'))
        return qs

    def list(self, request):
        """Override to allow superuser listing (bypasses ListProtectedViewSet block)."""
        if request.user.is_superuser:  # type: ignore[union-attr]
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        return super().list(request)
