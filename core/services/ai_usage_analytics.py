# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
AI Usage Analytics Service

Provides aggregated AI usage data for organizations, courses, assignments,
and platform-wide views. Supports multiple time granularities (hourly, daily, monthly).
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Optional, Literal

from django.db.models import Sum, Count
from django.db.models.functions import TruncHour, TruncDay, TruncMonth
from django.utils import timezone

from core.models import AIUsageRecord


GranularityType = Literal['hourly', 'daily', 'monthly']


def _get_default_date_range(granularity: GranularityType):
    """Return sensible default date ranges based on granularity."""
    now = timezone.now()
    if granularity == 'hourly':
        return now - timedelta(hours=48), now
    elif granularity == 'daily':
        return now - timedelta(days=30), now
    else:  # monthly
        return now - timedelta(days=365), now


def _get_trunc_function(granularity: GranularityType):
    """Return the appropriate Django truncation function for time bucketing."""
    if granularity == 'hourly':
        return TruncHour
    elif granularity == 'daily':
        return TruncDay
    else:
        return TruncMonth


def _projection_map(queryset, group_fields, rates_for_org):
    """Compute projected cost (token sums x current rates) grouped by group_fields.

    Rates are constant per (model, provider), so summing per-record costs equals
    pricing the token sums of each (group, model, provider, organization) cell.
    Returns {(group values tuple): Decimal cost}.
    """
    from core.services.ai_service import AIService

    rows = (
        queryset
        .values(*group_fields, 'model', 'provider', 'organization_id')
        .annotate(
            in_sum=Sum('input_tokens'),
            out_sum=Sum('output_tokens'),
            cached_sum=Sum('cached_tokens'),
        )
    )
    out: dict[tuple, Decimal] = defaultdict(lambda: Decimal('0'))
    for r in rows:
        cost = AIService.estimate_cost(
            r['provider'] or '', r['model'] or '',
            r['in_sum'] or 0, r['out_sum'] or 0,
            custom_rates=rates_for_org(r['organization_id']),
            cached_tokens=r['cached_sum'] or 0,
        )
        out[tuple(r[f] for f in group_fields)] += Decimal(str(cost))
    return out


def get_usage_summary(
    queryset=None,
    granularity: GranularityType = 'daily',
    start_date=None,
    end_date=None,
    breakdown_field: Optional[str] = None,
    breakdown_name_field: Optional[str] = None,
    breakdown_extra_fields: Optional[list[str]] = None,
    breakdown_name_formatter=None,
    projection_rates: Optional[dict] = None,
    projection_rates_per_org: bool = False,
):
    """
    Build an aggregated usage summary from AIUsageRecord queryset.

    Args:
        queryset: Pre-filtered AIUsageRecord queryset. If None, uses all records.
        granularity: 'hourly', 'daily', or 'monthly'
        start_date: Start of the range (inclusive). Defaults based on granularity.
        end_date: End of the range (inclusive). Defaults to now.
        breakdown_field: Foreign key field name to break down by (e.g., 'course', 'assignment')
        breakdown_name_field: Dot-separated path to the name field for breakdown labels
                              (e.g., 'course__name', 'assignment__name')
        breakdown_extra_fields: Additional fields to include in the breakdown query
                                (e.g., ['course__period'])
        breakdown_name_formatter: Optional callable(entry) -> str to format the breakdown name.
                                  Receives the raw query entry dict. If not provided, uses
                                  breakdown_name_field value directly.
        projection_rates: Merged custom token rates ({"model": {"input", "output"}})
                          applied to the whole queryset when computing projectedCost.
                          Falls back to hardcoded defaults when None.
        projection_rates_per_org: Resolve each organization's own ai_token_rates
                                  instead (platform-wide scope).

    Returns:
        dict with keys: totalTokens, inputTokens, outputTokens, estimatedCost,
                        projectedCost, requestCount, timeSeries, breakdown,
                        granularity, startDate, endDate
    """
    if queryset is None:
        queryset = AIUsageRecord.objects.all()

    default_start, default_end = _get_default_date_range(granularity)
    start_date = start_date or default_start
    end_date = end_date or default_end

    # Snap bare-date end values (midnight) to end-of-day so the date is inclusive.
    # Clients (e.g. date pickers without a time component) often send
    # "2026-03-31T00:00:00Z" meaning "through March 31", but a naive lte filter
    # would exclude every record created after midnight on that day.
    if (end_date.hour == 0 and end_date.minute == 0
            and end_date.second == 0 and end_date.microsecond == 0):
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Apply date filter
    queryset = queryset.filter(created__gte=start_date, created__lte=end_date)

    # Rate resolver for projected cost (usage priced at *current* rates,
    # unlike estimatedCost which is frozen at request time).
    if projection_rates_per_org:
        from core.models import Organization
        org_ids = queryset.exclude(organization__isnull=True).values_list(
            'organization_id', flat=True).distinct()
        org_rates = {
            o['id']: o['ai_token_rates']
            for o in Organization.objects.filter(id__in=org_ids).values('id', 'ai_token_rates')
        }
        def rates_for_org(org_id):
            return org_rates.get(org_id) or None
    else:
        def rates_for_org(org_id):
            return projection_rates

    # Grand totals
    totals = queryset.aggregate(
        total_tokens=Sum('total_tokens'),
        input_tokens=Sum('input_tokens'),
        output_tokens=Sum('output_tokens'),
        cached_tokens=Sum('cached_tokens'),
        estimated_cost=Sum('estimated_cost'),
        request_count=Count('id'),
    )

    # Time series
    trunc_fn = _get_trunc_function(granularity)
    time_series_qs = (
        queryset
        .annotate(period=trunc_fn('created'))
        .values('period')
        .annotate(
            totalTokens=Sum('total_tokens'),
            inputTokens=Sum('input_tokens'),
            outputTokens=Sum('output_tokens'),
            estimatedCost=Sum('estimated_cost'),
            requestCount=Count('id'),
        )
        .order_by('period')
    )

    time_series_projection = _projection_map(
        queryset.annotate(period=trunc_fn('created')), ['period'], rates_for_org)

    time_series = [
        {
            'period': entry['period'],
            'totalTokens': entry['totalTokens'] or 0,
            'inputTokens': entry['inputTokens'] or 0,
            'outputTokens': entry['outputTokens'] or 0,
            'estimatedCost': str(entry['estimatedCost'] or Decimal('0')),
            'projectedCost': str(time_series_projection.get((entry['period'],), Decimal('0'))),
            'requestCount': entry['requestCount'] or 0,
        }
        for entry in time_series_qs
    ]

    # Breakdown
    breakdown = []
    if breakdown_field and breakdown_name_field:
        values_fields = [f'{breakdown_field}_id', breakdown_name_field]
        if breakdown_extra_fields:
            values_fields.extend(breakdown_extra_fields)
        breakdown_qs = (
            queryset
            .values(*values_fields)
            .annotate(
                totalTokens=Sum('total_tokens'),
                inputTokens=Sum('input_tokens'),
                outputTokens=Sum('output_tokens'),
                estimatedCost=Sum('estimated_cost'),
                requestCount=Count('id'),
            )
            .order_by('-totalTokens')
        )

        breakdown_projection = _projection_map(
            queryset, [f'{breakdown_field}_id'], rates_for_org)

        for entry in breakdown_qs:
            if breakdown_name_formatter:
                name = breakdown_name_formatter(entry)
            else:
                name = entry[breakdown_name_field] or 'Unknown'
            breakdown.append({
                'id': entry[f'{breakdown_field}_id'],
                'name': name,
                'totalTokens': entry['totalTokens'] or 0,
                'inputTokens': entry['inputTokens'] or 0,
                'outputTokens': entry['outputTokens'] or 0,
                'estimatedCost': str(entry['estimatedCost'] or Decimal('0')),
                'projectedCost': str(breakdown_projection.get((entry[f'{breakdown_field}_id'],), Decimal('0'))),
                'requestCount': entry['requestCount'] or 0,
            })

    # Model breakdown — always computed, grouped by the model field
    model_breakdown_qs = (
        queryset
        .values('model')
        .annotate(
            totalTokens=Sum('total_tokens'),
            inputTokens=Sum('input_tokens'),
            outputTokens=Sum('output_tokens'),
            estimatedCost=Sum('estimated_cost'),
            requestCount=Count('id'),
        )
        .order_by('-totalTokens')
    )
    model_projection = _projection_map(queryset, ['model'], rates_for_org)
    model_breakdown = [
        {
            'id': None,
            'name': entry['model'] or 'Unknown',
            'totalTokens': entry['totalTokens'] or 0,
            'inputTokens': entry['inputTokens'] or 0,
            'outputTokens': entry['outputTokens'] or 0,
            'estimatedCost': str(entry['estimatedCost'] or Decimal('0')),
            'projectedCost': str(model_projection.get((entry['model'],), Decimal('0'))),
            'requestCount': entry['requestCount'] or 0,
        }
        for entry in model_breakdown_qs
    ]

    # Feature breakdown — always computed, grouped by request type and
    # labeled with the display name from REQUEST_TYPE_CHOICES.
    request_type_labels = dict(AIUsageRecord.REQUEST_TYPE_CHOICES)
    feature_breakdown_qs = (
        queryset
        .values('request_type')
        .annotate(
            totalTokens=Sum('total_tokens'),
            inputTokens=Sum('input_tokens'),
            outputTokens=Sum('output_tokens'),
            estimatedCost=Sum('estimated_cost'),
            requestCount=Count('id'),
        )
        .order_by('-totalTokens')
    )
    feature_projection = _projection_map(queryset, ['request_type'], rates_for_org)
    feature_breakdown = [
        {
            'id': None,
            'name': request_type_labels.get(entry['request_type'], entry['request_type'] or 'Unknown'),
            'totalTokens': entry['totalTokens'] or 0,
            'inputTokens': entry['inputTokens'] or 0,
            'outputTokens': entry['outputTokens'] or 0,
            'estimatedCost': str(entry['estimatedCost'] or Decimal('0')),
            'projectedCost': str(feature_projection.get((entry['request_type'],), Decimal('0'))),
            'requestCount': entry['requestCount'] or 0,
        }
        for entry in feature_breakdown_qs
    ]

    return {
        'totalTokens': totals['total_tokens'] or 0,
        'inputTokens': totals['input_tokens'] or 0,
        'outputTokens': totals['output_tokens'] or 0,
        'cachedTokens': totals['cached_tokens'] or 0,
        'estimatedCost': str(totals['estimated_cost'] or Decimal('0')),
        'projectedCost': str(sum(model_projection.values(), Decimal('0'))),
        'requestCount': totals['request_count'] or 0,
        'timeSeries': time_series,
        'breakdown': breakdown,
        'modelBreakdown': model_breakdown,
        'featureBreakdown': feature_breakdown,
        'granularity': granularity,
        'startDate': start_date,
        'endDate': end_date,
    }
