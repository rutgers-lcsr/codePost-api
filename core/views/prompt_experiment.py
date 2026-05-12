# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.core.cache import cache as django_cache
from django.db.models import Count, Case, When, IntegerField
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from core.models import PromptExperiment, PromptFeedback, SuggestedComment
from core.serializers.prompt_experiment import (
    PromptExperimentSerializer,
    PromptExperimentResultsSerializer,
)
from core.views.template import SuperUserListProtectedViewSet, ListPagination

from logging import getLogger
logger = getLogger(__name__)


class PromptExperimentViewSet(SuperUserListProtectedViewSet):
    """
    CRUD and lifecycle management for A/B prompt experiments.

    Superuser-only.  Only one experiment per prompt_type may be 'running'
    at a time (enforced at the DB level).

    list:
    List all experiments. Supports ?promptType= and ?status= filters.

    create:
    Create a new experiment (defaults to 'paused').

    retrieve / update / partial_update / delete:
    Standard CRUD.
    """
    queryset = PromptExperiment.objects.select_related(
        'variant_a', 'variant_b', 'started_by',
    ).all()
    serializer_class = PromptExperimentSerializer
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

    @extend_schema(
        request=None,
        responses=PromptExperimentSerializer,
        description="Start (resume) this experiment so it begins sampling requests.",
    )
    @action(detail=True, methods=['POST'])
    def resume(self, request, pk=None):
        experiment = self.get_object()
        if experiment.status == 'completed':
            return Response(
                {'error': 'Cannot resume a completed experiment.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        experiment.status = 'running'
        experiment.save()
        django_cache.delete(f'running_experiment:{experiment.prompt_type}')
        logger.info(f"Experiment {experiment.id} resumed by {request.user.email}")
        return Response(PromptExperimentSerializer(experiment).data)

    @extend_schema(
        request=None,
        responses=PromptExperimentSerializer,
        description="Pause this experiment (no new A/B requests will be triggered).",
    )
    @action(detail=True, methods=['POST'])
    def pause(self, request, pk=None):
        experiment = self.get_object()
        if experiment.status != 'running':
            return Response(
                {'error': 'Only running experiments can be paused.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        experiment.status = 'paused'
        experiment.save()
        django_cache.delete(f'running_experiment:{experiment.prompt_type}')
        logger.info(f"Experiment {experiment.id} paused by {request.user.email}")
        return Response(PromptExperimentSerializer(experiment).data)

    @extend_schema(
        request=None,
        responses=PromptExperimentSerializer,
        parameters=[
            OpenApiParameter(
                name='promoteWinner', required=False, type=bool,
                description="If true, activate the winning variant.",
            ),
        ],
        description="Mark this experiment as completed. Optionally promote the winner.",
    )
    @action(detail=True, methods=['POST'])
    def complete(self, request, pk=None):
        experiment = self.get_object()
        experiment.status = 'completed'
        experiment.completed_at = timezone.now()
        experiment.save()
        django_cache.delete(f'running_experiment:{experiment.prompt_type}')

        # Optionally promote the winner
        promote = request.query_params.get('promoteWinner', '').lower() in ('true', '1')
        promoted_variant = None
        promotion_warning = None
        if promote:
            results = self._aggregate_results(experiment)
            behavioral = results.get('behavioral', {})
            winner = None
            if results['variantAWins'] > results['variantBWins']:
                winner = experiment.variant_a
            elif results['variantBWins'] > results['variantAWins']:
                winner = experiment.variant_b

            # Behavioral gate: check that behavioral data agrees (or is insufficient)
            if winner and behavioral:
                a_confident = behavioral.get('variantAConfident', False)
                b_confident = behavioral.get('variantBConfident', False)

                if a_confident and b_confident:
                    a_rate = behavioral.get('variantA', {}).get('acceptanceRate')
                    b_rate = behavioral.get('variantB', {}).get('acceptanceRate')
                    if a_rate is not None and b_rate is not None:
                        behavioral_winner_is_a = a_rate > b_rate
                        explicit_winner_is_a = (winner == experiment.variant_a)
                        if behavioral_winner_is_a != explicit_winner_is_a:
                            promotion_warning = (
                                'Explicit feedback and behavioral metrics disagree on the winner. '
                                f'Explicit winner: variant {"A" if explicit_winner_is_a else "B"}, '
                                f'Behavioral acceptance rate: A={a_rate}, B={b_rate}. '
                                'Promotion skipped — review results manually.'
                            )
                            logger.warning(
                                f"Experiment {experiment.id}: promotion skipped due to disagreement. "
                                f"{promotion_warning}"
                            )
                            winner = None
                elif not a_confident or not b_confident:
                    promotion_warning = (
                        'Insufficient behavioral data for confident promotion. '
                        f'Variant A samples: {behavioral.get("variantA", {}).get("total", 0)}, '
                        f'Variant B samples: {behavioral.get("variantB", {}).get("total", 0)}. '
                        'Promoting based on explicit feedback only.'
                    )
                    logger.info(
                        f"Experiment {experiment.id}: promoting with low behavioral confidence. "
                        f"{promotion_warning}"
                    )

            if winner:
                from core.models import SystemPromptVariant
                SystemPromptVariant.objects.filter(
                    prompt_type=experiment.prompt_type, status='active',
                ).exclude(pk=winner.pk).update(status='retired')
                winner.status = 'active'
                winner.save()
                django_cache.delete(f'active_prompt:{experiment.prompt_type}')
                promoted_variant = winner.id
                logger.info(
                    f"Experiment {experiment.id} completed — variant {winner.id} promoted "
                    f"by {request.user.email}"
                )

        data = PromptExperimentSerializer(experiment).data
        if promoted_variant:
            data['promotedVariant'] = promoted_variant
        if promotion_warning:
            data['promotionWarning'] = promotion_warning
        return Response(data)

    @extend_schema(
        responses=PromptExperimentResultsSerializer,
        parameters=[
            OpenApiParameter(
                name='pool', required=False, type=str,
                description="Filter feedback pool: 'default', 'custom', or 'all'.",
                enum=['default', 'custom', 'all'],
            ),
            OpenApiParameter(
                name='minAssignments', required=False, type=int,
                description="Minimum distinct assignments required for behavioral metrics (default: 1).",
            ),
            OpenApiParameter(
                name='minSamplesPerVariant', required=False, type=int,
                description="Minimum suggestions per variant for confident metrics (default: 30).",
            ),
        ],
        description="Get aggregated feedback results for this experiment, including behavioral metrics.",
    )
    @action(detail=True, methods=['GET'])
    def results(self, request, pk=None):
        experiment = self.get_object()
        pool = request.query_params.get('pool', 'all')
        min_assignments = int(request.query_params.get('minAssignments', '1'))
        min_samples = int(request.query_params.get('minSamplesPerVariant', '30'))
        results = self._aggregate_results(
            experiment, pool=pool,
            min_assignments=min_assignments, min_samples_per_variant=min_samples,
        )
        return Response(results)

    @staticmethod
    def _aggregate_results(
        experiment: PromptExperiment,
        pool: str = 'all',
        min_assignments: int = 1,
        min_samples_per_variant: int = 30,
    ) -> dict:
        """Aggregate explicit feedback and behavioral metrics for a given experiment."""
        # --- Explicit feedback (existing) ---
        qs = PromptFeedback.objects.filter(experiment=experiment)
        if pool == 'default':
            qs = qs.filter(is_custom_context=False)
        elif pool == 'custom':
            qs = qs.filter(is_custom_context=True)

        agg = qs.aggregate(
            total=Count('id'),
            a_wins=Count(
                Case(When(chosen_variant=experiment.variant_a, then=1), output_field=IntegerField())
            ),
            b_wins=Count(
                Case(When(chosen_variant=experiment.variant_b, then=1), output_field=IntegerField())
            ),
            default_count=Count(Case(When(is_custom_context=False, then=1), output_field=IntegerField())),
            custom_count=Count(Case(When(is_custom_context=True, then=1), output_field=IntegerField())),
            thumbs_up=Count(Case(When(rating=1, then=1), output_field=IntegerField())),
            thumbs_down=Count(Case(When(rating=-1, then=1), output_field=IntegerField())),
        )

        ties = agg['total'] - agg['a_wins'] - agg['b_wins']

        result = {
            'experimentId': experiment.id,
            'promptType': experiment.prompt_type,
            'totalFeedback': agg['total'],
            'variantAWins': agg['a_wins'],
            'variantBWins': agg['b_wins'],
            'ties': max(0, ties),
            'defaultPoolCount': agg['default_count'],
            'customPoolCount': agg['custom_count'],
            'thumbsUp': agg['thumbs_up'],
            'thumbsDown': agg['thumbs_down'],
        }

        # --- Behavioral metrics ---
        result['behavioral'] = PromptExperimentViewSet._aggregate_behavioral(
            experiment, min_assignments, min_samples_per_variant,
        )

        return result

    @staticmethod
    def _variant_suggestion_stats(variant_id: int) -> dict:
        """Compute suggestion-level behavioral stats for a single variant."""
        qs = SuggestedComment.objects.filter(promptVariant_id=variant_id)
        total = qs.count()
        if total == 0:
            return {
                'total': 0, 'accepted': 0, 'rejected': 0, 'pending': 0,
                'acceptanceRate': None, 'rejectionRate': None,
                'editRate': None, 'avgTimeToDecideSeconds': None,
                'distinctAssignments': 0,
            }

        status_counts = qs.aggregate(
            accepted=Count(Case(When(status='accepted', then=1), output_field=IntegerField())),
            rejected=Count(Case(When(status='rejected', then=1), output_field=IntegerField())),
            pending=Count(Case(When(status='pending', then=1), output_field=IntegerField())),
        )

        accepted = status_counts['accepted']
        rejected = status_counts['rejected']
        pending = status_counts['pending']
        acted = accepted + rejected

        acceptance_rate = accepted / acted if acted > 0 else None
        rejection_rate = rejected / acted if acted > 0 else None

        # Edit rate: of accepted suggestions, how many had text modified post-acceptance?
        accepted_with_comment = qs.filter(
            status='accepted', acceptedComment__isnull=False,
        ).select_related('acceptedComment')
        edited_count = sum(
            1 for s in accepted_with_comment.iterator()
            if s.acceptedComment and s.text != s.acceptedComment.text
        )
        edit_rate = edited_count / accepted if accepted > 0 else None

        # Average time to decide: firstViewedAt -> acceptedComment.created
        viewed_and_accepted = accepted_with_comment.filter(
            firstViewedAt__isnull=False,
        )
        time_deltas = []
        for s in viewed_and_accepted.iterator():
            if s.acceptedComment and s.firstViewedAt:
                delta = (s.acceptedComment.created - s.firstViewedAt).total_seconds()
                if delta >= 0:
                    time_deltas.append(delta)
        avg_time = sum(time_deltas) / len(time_deltas) if time_deltas else None

        distinct_assignments = qs.values('submission__assignment').distinct().count()

        return {
            'total': total,
            'accepted': accepted,
            'rejected': rejected,
            'pending': pending,
            'acceptanceRate': round(acceptance_rate, 4) if acceptance_rate is not None else None,
            'rejectionRate': round(rejection_rate, 4) if rejection_rate is not None else None,
            'editRate': round(edit_rate, 4) if edit_rate is not None else None,
            'avgTimeToDecideSeconds': round(avg_time, 1) if avg_time is not None else None,
            'distinctAssignments': distinct_assignments,
        }

    @staticmethod
    def _aggregate_behavioral(
        experiment: PromptExperiment,
        min_assignments: int = 1,
        min_samples_per_variant: int = 30,
    ) -> dict:
        """Aggregate behavioral metrics for both variants of an experiment."""
        variant_a_stats = PromptExperimentViewSet._variant_suggestion_stats(
            experiment.variant_a_id,
        )
        variant_b_stats = PromptExperimentViewSet._variant_suggestion_stats(
            experiment.variant_b_id,
        )

        a_confident = (
            variant_a_stats['total'] >= min_samples_per_variant
            and variant_a_stats['distinctAssignments'] >= min_assignments
        )
        b_confident = (
            variant_b_stats['total'] >= min_samples_per_variant
            and variant_b_stats['distinctAssignments'] >= min_assignments
        )

        # Batch acceptance rate: average proportion of accepted suggestions per batch
        batch_rates = {}
        for label, vid in [('variantA', experiment.variant_a_id), ('variantB', experiment.variant_b_id)]:
            batches = (
                SuggestedComment.objects
                .filter(promptVariant_id=vid, generationBatch__isnull=False)
                .exclude(status='pending')  # only count batches where grader acted
                .values('generationBatch')
                .annotate(
                    batch_total=Count('id'),
                    batch_accepted=Count(Case(When(status='accepted', then=1), output_field=IntegerField())),
                )
            )
            rates = [
                b['batch_accepted'] / b['batch_total']
                for b in batches if b['batch_total'] > 0
            ]
            batch_rates[label] = round(sum(rates) / len(rates), 4) if rates else None

        return {
            'variantA': variant_a_stats,
            'variantB': variant_b_stats,
            'variantAConfident': a_confident,
            'variantBConfident': b_confident,
            'batchAcceptanceRateA': batch_rates.get('variantA'),
            'batchAcceptanceRateB': batch_rates.get('variantB'),
            'minAssignmentsThreshold': min_assignments,
            'minSamplesThreshold': min_samples_per_variant,
        }
