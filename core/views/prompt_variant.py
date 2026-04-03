# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.core.cache import cache as django_cache
from django.db.models import Count, Case, When, IntegerField
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from core.models import SystemPromptVariant, PromptLabSettings, PromptFeedback, SuggestedComment
from core.serializers.prompt_variant import (
    SystemPromptVariantSerializer,
    SystemPromptVariantSummarySerializer,
)
from core.views.template import SuperUserListProtectedViewSet, ListPagination

from logging import getLogger
logger = getLogger(__name__)


def _serialize_settings(settings: PromptLabSettings) -> dict:
    """Build the camelCase response dict for PromptLabSettings."""
    return {
        'autoImproveEnabled': settings.auto_improve_enabled,
        'scheduleEnabled': settings.schedule_enabled,
        'scheduleIntervalHours': settings.schedule_interval_hours,
        'thresholdEnabled': settings.threshold_enabled,
        'feedbackThreshold': settings.feedback_threshold,
        'minFeedback': settings.min_feedback,
        'aiProvider': settings.ai_provider,
        'aiModel': settings.ai_model,
        # Never return the raw key — only whether one is set
        'aiApiKeySet': bool(settings.ai_api_key),
    }


class SystemPromptVariantViewSet(SuperUserListProtectedViewSet):
    """
    CRUD for platform-global AI system prompt variants.

    Superuser-only.  Use the ``activate`` action to promote a variant as the
    active prompt for its type (retiring the previous active variant).

    list:
    List all prompt variants (superuser only). Supports ?promptType= filter.

    retrieve:
    Return a single variant.

    create:
    Create a new variant (status defaults to 'draft').

    update / partial_update:
    Edit a variant. Cannot edit an 'active' variant directly —
    clone it first, edit the clone, then activate the clone.

    delete:
    Delete a variant. Active variants cannot be deleted.
    """
    queryset = SystemPromptVariant.objects.select_related('parent', 'created_by').all()
    serializer_class = SystemPromptVariantSerializer
    permission_classes = (IsAuthenticated, IsAdminUser)
    pagination_class = ListPagination

    def get_queryset(self):
        qs = super().get_queryset()
        prompt_type = self.request.query_params.get('promptType')
        if prompt_type:
            qs = qs.filter(prompt_type=prompt_type)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def perform_destroy(self, instance):
        if instance.status == 'active':
            raise Exception("Cannot delete an active variant. Retire it first.")
        instance.delete()

    @extend_schema(
        request=None,
        responses=SystemPromptVariantSerializer,
        description=(
            "Set this variant as the active prompt for its type. "
            "The previously active variant (if any) is moved to 'retired'."
        ),
    )
    @action(detail=True, methods=['POST'])
    def activate(self, request, pk=None):
        variant = self.get_object()

        # Retire any currently active variant for the same prompt_type
        SystemPromptVariant.objects.filter(
            prompt_type=variant.prompt_type, status='active',
        ).exclude(pk=variant.pk).update(status='retired')

        variant.status = 'active'
        variant.save()

        # Bust cache
        django_cache.delete(f'active_prompt:{variant.prompt_type}')

        logger.info(
            f"Prompt variant {variant.id} ({variant.name}) activated for "
            f"{variant.prompt_type} by {request.user.email}"
        )
        return Response(SystemPromptVariantSerializer(variant).data)

    @extend_schema(
        request=None,
        responses=SystemPromptVariantSerializer,
        description="Clone this variant as a new draft for editing.",
    )
    @action(detail=True, methods=['POST'])
    def clone(self, request, pk=None):
        original = self.get_object()

        clone = SystemPromptVariant.objects.create(
            prompt_type=original.prompt_type,
            name=f"{original.name} (clone)",
            text=original.text,
            status='draft',
            version=original.version + 1,
            parent=original,
            created_by=request.user,
            metadata={
                **original.metadata,
                'cloned_from': original.id,
            },
        )
        logger.info(
            f"Prompt variant {original.id} cloned as {clone.id} by {request.user.email}"
        )
        return Response(
            SystemPromptVariantSerializer(clone).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=None,
        responses=SystemPromptVariantSerializer,
        description=(
            "Analyze feedback for a prompt type and use AI to generate an "
            "improved variant. Creates a new draft child of the current active "
            "variant."
        ),
        parameters=[
            OpenApiParameter(
                name='promptType',
                type=str,
                location='query',
                required=True,
                description='The prompt type to auto-improve.',
            ),
        ],
    )
    @action(detail=False, methods=['POST'], url_path='auto-improve')
    def auto_improve(self, request):
        from core.services.prompt_improvement import auto_improve_prompt

        prompt_type = request.query_params.get('promptType')
        if not prompt_type:
            return Response(
                {'detail': 'promptType query parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_types = {c[0] for c in SystemPromptVariant.PROMPT_TYPE_CHOICES}
        if prompt_type not in valid_types:
            return Response(
                {'detail': f'Invalid promptType. Must be one of: {", ".join(sorted(valid_types))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        settings = PromptLabSettings.load()

        try:
            new_variant = auto_improve_prompt(
                prompt_type,
                min_feedback=settings.min_feedback,
                triggered_by='manual',
                user=request.user,
            )
        except Exception as e:
            logger.exception(f"Auto-improve AI call failed for {prompt_type}")
            return Response(
                {'detail': f'AI generation failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if new_variant is None:
            return Response(
                {
                    'detail': (
                        f'Not enough feedback to auto-improve. '
                        f'Need at least {settings.min_feedback}.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            SystemPromptVariantSerializer(new_variant).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=None,
        responses={200: dict},
        description=(
            "Get performance stats for this prompt variant: behavioral metrics "
            "(acceptance/rejection/edit rates, time to decide) and explicit "
            "feedback (thumbs up/down)."
        ),
    )
    @action(detail=True, methods=['GET'])
    def stats(self, request, pk=None):
        """Return behavioral + explicit feedback stats for a single variant."""
        from core.views.prompt_experiment import PromptExperimentViewSet

        variant = self.get_object()

        # Behavioral metrics (reuse the existing per-variant computation)
        behavioral = PromptExperimentViewSet._variant_suggestion_stats(variant.id)

        # Batch acceptance rate
        batches = (
            SuggestedComment.objects
            .filter(promptVariant=variant, generationBatch__isnull=False)
            .exclude(status='pending')
            .values('generationBatch')
            .annotate(
                batch_total=Count('id'),
                batch_accepted=Count(Case(When(status='accepted', then=1), output_field=IntegerField())),
            )
        )
        batch_rates = [
            b['batch_accepted'] / b['batch_total']
            for b in batches if b['batch_total'] > 0
        ]
        behavioral['batchAcceptanceRate'] = (
            round(sum(batch_rates) / len(batch_rates), 4) if batch_rates else None
        )

        # Explicit feedback aggregation
        feedback_qs = PromptFeedback.objects.filter(variant_used=variant)
        feedback_agg = feedback_qs.aggregate(
            total=Count('id'),
            thumbs_up=Count(Case(When(rating=1, then=1), output_field=IntegerField())),
            thumbs_down=Count(Case(When(rating=-1, then=1), output_field=IntegerField())),
        )

        return Response({
            'variantId': variant.id,
            'variantName': variant.name,
            'promptType': variant.prompt_type,
            'status': variant.status,
            'behavioral': behavioral,
            'explicitFeedback': {
                'total': feedback_agg['total'],
                'thumbsUp': feedback_agg['thumbs_up'],
                'thumbsDown': feedback_agg['thumbs_down'],
            },
        })

    # ─── Prompt Lab Settings ───────────────────────────────────────────────

    @extend_schema(
        request=None,
        responses={200: dict},
        description="Get the current Prompt Lab auto-improvement settings.",
    )
    @action(detail=False, methods=['GET'], url_path='settings')
    def get_settings(self, request):
        settings = PromptLabSettings.load()
        return Response(_serialize_settings(settings))

    @extend_schema(
        request=dict,
        responses={200: dict},
        description="Update Prompt Lab auto-improvement settings.",
    )
    @action(detail=False, methods=['PUT'], url_path='settings/update')
    def update_settings(self, request):
        settings = PromptLabSettings.load()
        data = request.data

        field_map = {
            'autoImproveEnabled': 'auto_improve_enabled',
            'scheduleEnabled': 'schedule_enabled',
            'scheduleIntervalHours': 'schedule_interval_hours',
            'thresholdEnabled': 'threshold_enabled',
            'feedbackThreshold': 'feedback_threshold',
            'minFeedback': 'min_feedback',
            'aiProvider': 'ai_provider',
            'aiModel': 'ai_model',
        }

        for camel, snake in field_map.items():
            if camel in data:
                setattr(settings, snake, data[camel])

        # Handle API key separately — only update if a non-empty value is sent
        if 'aiApiKey' in data and data['aiApiKey']:
            settings.ai_api_key = data['aiApiKey']

        settings.save()

        logger.info(
            f"Prompt Lab settings updated by {request.user.email}: "
            f"enabled={settings.auto_improve_enabled}, "
            f"schedule={settings.schedule_enabled}/{settings.schedule_interval_hours}h, "
            f"threshold={settings.threshold_enabled}/{settings.feedback_threshold}, "
            f"ai={settings.ai_provider}/{settings.ai_model}"
        )

        return Response(_serialize_settings(settings))
