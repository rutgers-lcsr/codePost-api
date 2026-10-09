# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Aggregation queries for the superadmin autograding stats endpoint.
"""
from django.db.models import Count, Q

from core.models import AutograderExecutionEvent

TOP_ERRORS_LIMIT = 10
TOP_ASSIGNMENTS_LIMIT = 10


def _language_label(language):
  return language or 'unknown'


def get_autograding_stats(date_from, date_to):
  """Aggregate AutograderExecutionEvent rows in [date_from, date_to)."""
  qs = AutograderExecutionEvent.objects.filter(created__gte=date_from, created__lt=date_to)

  totals = qs.aggregate(
      total=Count('id'),
      cache_hits=Count('id', filter=Q(cached=True)),
      executions=Count('id', filter=Q(cached=False)),
      failures=Count('id', filter=Q(cached=False, success=False)),
  )
  total = totals['total']
  cache_hit_rate = round(totals['cache_hits'] / total, 4) if total else 0.0

  language_usage = [
      {'language': _language_label(row['language']), 'count': row['count']}
      for row in qs.values('language').annotate(count=Count('id')).order_by('-count')
  ]

  failures_per_language = [
      {
          'language': _language_label(row['language']),
          'executions': row['executions'],
          'failures': row['failures'],
          'failureRate': round(row['failures'] / row['executions'], 4),
      }
      for row in (
          qs.filter(cached=False).values('language')
            .annotate(executions=Count('id'), failures=Count('id', filter=Q(success=False)))
            .filter(failures__gt=0).order_by('-failures')
      )
  ]

  failed_qs = qs.filter(cached=False, success=False)
  top_errors = []
  for row in (failed_qs.values('error_category')
              .annotate(count=Count('id')).order_by('-count')[:TOP_ERRORS_LIMIT]):
    sample = (failed_qs.filter(error_category=row['error_category'])
              .exclude(error_message='')
              .order_by('-created')
              .values_list('error_message', flat=True).first()) or ''
    top_errors.append({
        'category': row['error_category'] or 'unknown',
        'count': row['count'],
        'sampleMessage': sample,
    })

  failures_by_assignment = []
  for row in (failed_qs.filter(assignment__isnull=False)
              .values('assignment_id', 'assignment__name',
                      'course_id', 'course__name', 'course__period')
              .annotate(failures=Count('id')).order_by('-failures')[:TOP_ASSIGNMENTS_LIMIT]):
    top_category = (failed_qs.filter(assignment_id=row['assignment_id'])
                    .values('error_category').annotate(count=Count('id'))
                    .order_by('-count').values_list('error_category', flat=True).first())
    failures_by_assignment.append({
        'courseId': row['course_id'],
        'courseName': row['course__name'],
        'coursePeriod': row['course__period'],
        'assignmentId': row['assignment_id'],
        'assignmentName': row['assignment__name'],
        'failures': row['failures'],
        'topCategory': top_category or 'unknown',
    })

  return {
      'dateFrom': date_from,
      'dateTo': date_to,
      'totalRequests': total,
      'cacheHits': totals['cache_hits'],
      'actualExecutions': totals['executions'],
      'cacheHitRate': cache_hit_rate,
      'failedExecutions': totals['failures'],
      'languageUsage': language_usage,
      'failuresPerLanguage': failures_per_language,
      'topErrors': top_errors,
      'failuresByAssignment': failures_by_assignment,
  }


def get_autograding_failures(date_from, date_to, *, category=None, trigger=None, language=None,
                             course_id=None, assignment_id=None, q=None):
  """Failed (non-cached) executions in [date_from, date_to), newest first.

  Filters are AND-ed; `language='unknown'` matches the empty snapshot and `q`
  is a case-insensitive substring match on the error text.
  """
  qs = (AutograderExecutionEvent.objects
        .filter(created__gte=date_from, created__lt=date_to, cached=False, success=False)
        .select_related('course', 'assignment', 'triggered_by'))
  if category:
    qs = qs.filter(error_category=category)
  if trigger:
    qs = qs.filter(trigger=trigger)
  if language:
    qs = qs.filter(language='' if language == 'unknown' else language)
  if course_id:
    qs = qs.filter(course_id=course_id)
  if assignment_id:
    qs = qs.filter(assignment_id=assignment_id)
  if q:
    qs = qs.filter(Q(error_message__icontains=q) | Q(error_detail__icontains=q))
  return qs.order_by('-created', '-id')
