# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
AI Usage Analytics Service

Provides aggregated AI usage data for organizations, courses, assignments,
and platform-wide views. Supports multiple time granularities (hourly, daily, monthly).
"""

from datetime import timedelta
from decimal import Decimal
from typing import Optional, Literal

from django.db.models import Sum, Count, Q
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


def get_usage_summary(
    queryset=None,
    granularity: GranularityType = 'daily',
    start_date=None,
    end_date=None,
    breakdown_field: Optional[str] = None,
    breakdown_name_field: Optional[str] = None,
    breakdown_extra_fields: Optional[list[str]] = None,
    breakdown_name_formatter=None,
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

    Returns:
        dict with keys: totalTokens, inputTokens, outputTokens, estimatedCost,
                        requestCount, timeSeries, breakdown, granularity, startDate, endDate
    """
    if queryset is None:
        queryset = AIUsageRecord.objects.all()

    default_start, default_end = _get_default_date_range(granularity)
    start_date = start_date or default_start
    end_date = end_date or default_end

    # Apply date filter
    queryset = queryset.filter(created__gte=start_date, created__lte=end_date)

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

    time_series = [
        {
            'period': entry['period'],
            'totalTokens': entry['totalTokens'] or 0,
            'inputTokens': entry['inputTokens'] or 0,
            'outputTokens': entry['outputTokens'] or 0,
            'estimatedCost': str(entry['estimatedCost'] or Decimal('0')),
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
    model_breakdown = [
        {
            'id': None,
            'name': entry['model'] or 'Unknown',
            'totalTokens': entry['totalTokens'] or 0,
            'inputTokens': entry['inputTokens'] or 0,
            'outputTokens': entry['outputTokens'] or 0,
            'estimatedCost': str(entry['estimatedCost'] or Decimal('0')),
            'requestCount': entry['requestCount'] or 0,
        }
        for entry in model_breakdown_qs
    ]

    return {
        'totalTokens': totals['total_tokens'] or 0,
        'inputTokens': totals['input_tokens'] or 0,
        'outputTokens': totals['output_tokens'] or 0,
        'cachedTokens': totals['cached_tokens'] or 0,
        'estimatedCost': str(totals['estimated_cost'] or Decimal('0')),
        'requestCount': totals['request_count'] or 0,
        'timeSeries': time_series,
        'breakdown': breakdown,
        'modelBreakdown': model_breakdown,
        'granularity': granularity,
        'startDate': start_date,
        'endDate': end_date,
    }
