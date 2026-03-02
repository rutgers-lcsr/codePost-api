# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.decorators import api_view, permission_classes
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db import connection, DatabaseError
from log.models import Event
from django.core.paginator import Paginator
import time
import shutil

from core.serializers.system import SystemHealthResponseSerializer, SystemActivityResponseSerializer, MaintenanceBannerSerializer, MaintenanceBannerResponseSerializer


from djangorestframework_camel_case.render import CamelCaseJSONRenderer
from djangorestframework_camel_case.parser import CamelCaseJSONParser


def _check_database() -> dict:
    """Run a timed SELECT 1 to verify DB connectivity and measure latency."""
    t0 = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "status": "ok",
            "label": f"Connected ({latency_ms} ms)",
            "detail": None,
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        return {
            "status": "error",
            "label": "Disconnected",
            "detail": str(exc),
            "latency_ms": None,
        }


def _check_celery() -> dict:
    """Ping Celery workers with a short timeout and report the count."""
    try:
        from autograder.celery import app
        t0 = time.perf_counter()
        inspector = app.control.inspect(timeout=2.0)
        pong = inspector.ping()
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if pong:
            worker_count = len(pong)
            return {
                "status": "ok",
                "label": f"{worker_count} worker{'s' if worker_count != 1 else ''} online",
                "detail": None,
                "latency_ms": latency_ms,
                "worker_count": worker_count,
            }
        return {
            "status": "warning",
            "label": "No workers responded",
            "detail": "Celery ping returned no workers within 2 s.",
            "latency_ms": latency_ms,
            "worker_count": 0,
        }
    except Exception as exc:
        return {
            "status": "error",
            "label": "Error",
            "detail": str(exc),
            "latency_ms": None,
            "worker_count": None,
        }


def _check_cache() -> dict:
    """Write and read a test key through Django's configured cache backend."""
    from django.core.cache import cache
    key = "_system_health_probe"
    sentinel = "ok"
    t0 = time.perf_counter()
    try:
        cache.set(key, sentinel, timeout=5)
        result = cache.get(key)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if result == sentinel:
            return {
                "status": "ok",
                "label": f"Connected ({latency_ms} ms)",
                "detail": None,
                "latency_ms": latency_ms,
            }
        return {
            "status": "warning",
            "label": "Read-back mismatch",
            "detail": "Cache set/get returned unexpected value.",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        return {
            "status": "error",
            "label": "Error",
            "detail": str(exc),
            "latency_ms": None,
        }


def _check_migrations() -> dict:
    """Count unapplied migrations using Django's MigrationExecutor."""
    try:
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        pending = len(plan)
        if pending == 0:
            return {"status": "ok", "label": "Up to date", "detail": None, "pending": 0}
        return {
            "status": "warning",
            "label": f"{pending} pending",
            "detail": ", ".join(f"{a}.{n}" for a, n in [(m.app_label, m.name) for m, _ in plan[:5]]),
            "pending": pending,
        }
    except Exception as exc:
        return {"status": "error", "label": "Error", "detail": str(exc), "pending": -1}


def _check_disk() -> dict:
    """Check disk usage on the filesystem where this project lives."""
    try:
        import os
        from django.conf import settings as django_settings
        path = getattr(django_settings, "BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
        usage = shutil.disk_usage(str(path))
        used_pct = round(usage.used / usage.total * 100, 1)
        free_gb = round(usage.free / (1024 ** 3), 1)
        if used_pct >= 90:
            status = "error"
        elif used_pct >= 75:
            status = "warning"
        else:
            status = "ok"
        return {
            "status": status,
            "label": f"{used_pct}% used — {free_gb} GB free",
            "detail": None,
            "latency_ms": None,
            "used_pct": used_pct,
            "free_gb": free_gb,
        }
    except Exception as exc:
        return {
            "status": "error",
            "label": "Error",
            "detail": str(exc),
            "latency_ms": None,
            "used_pct": None,
            "free_gb": None,
        }


class SystemHealthView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    renderer_classes = [CamelCaseJSONRenderer]

    @extend_schema(responses={200: SystemHealthResponseSerializer})
    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta

        db = _check_database()
        celery = _check_celery()
        cache = _check_cache()
        migrations = _check_migrations()
        disk = _check_disk()

        # Recent event count (last hour) — best-effort
        try:
            since = timezone.now() - timedelta(hours=1)
            recent_events_1h = Event.objects.filter(created__gte=since).count()
        except Exception:
            recent_events_1h = -1

        # Overall status: worst of all checks
        all_statuses = [db["status"], celery["status"], cache["status"], migrations["status"], disk["status"]]
        if "error" in all_statuses:
            overall = "critical"
        elif "warning" in all_statuses:
            overall = "degraded"
        else:
            overall = "ok"

        return Response({
            "checked_at": timezone.now(),
            "overall": overall,
            "database": db,
            "celery": celery,
            "cache": cache,
            "migrations": migrations,
            "disk": disk,
            "recent_events_1h": recent_events_1h,
        })

class SystemActivityView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        responses={200: SystemActivityResponseSerializer},
        parameters=[
            OpenApiParameter(name="page", required=False, type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="pageSize", required=False, type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="category", required=False, type=str, location=OpenApiParameter.QUERY,
                             description="Filter by event category (exact match)"),
            OpenApiParameter(name="search", required=False, type=str, location=OpenApiParameter.QUERY,
                             description="Search across description, user, and meta fields"),
            OpenApiParameter(name="startDate", required=False, type=str, location=OpenApiParameter.QUERY,
                             description="Filter events created on or after this ISO 8601 datetime"),
            OpenApiParameter(name="endDate", required=False, type=str, location=OpenApiParameter.QUERY,
                             description="Filter events created on or before this ISO 8601 datetime"),
        ],
    )
    def get(self, request):
        # Fetch recent events
        page_size = int(request.query_params.get('pageSize', 20))
        page_num = int(request.query_params.get('page', 1))

        events = Event.objects.all().order_by('-created')

        # --- Filtering ---
        category = request.query_params.get('category', '').strip()
        if category:
            events = events.filter(category=category)

        search = request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q
            events = events.filter(
                Q(description__icontains=search) |
                Q(user__icontains=search) |
                Q(meta__icontains=search)
            )

        start_date = request.query_params.get('startDate', '').strip()
        if start_date:
            from django.utils.dateparse import parse_datetime
            parsed_start = parse_datetime(start_date)
            if parsed_start:
                events = events.filter(created__gte=parsed_start)

        end_date = request.query_params.get('endDate', '').strip()
        if end_date:
            from django.utils.dateparse import parse_datetime
            parsed_end = parse_datetime(end_date)
            if parsed_end:
                events = events.filter(created__lte=parsed_end)

        paginator = Paginator(events, page_size)
        page = paginator.get_page(page_num)

        data = []
        for event in page:
            data.append({
                "id": event.id,
                "category": event.category,
                "description": event.description,
                "created": event.created,
                "meta": event.meta,
                "courseID": event.courseID,
                "user": event.user
            })

        return Response({
            "results": data,
            "total": paginator.count,
            "page": page_num,
            "pages": paginator.num_pages
        })


class SystemBannerView(APIView):
    """
    GET  /system/banner/   — public, no auth required.
    PATCH /system/banner/  — admin only; update banner fields.
    """
    renderer_classes = [CamelCaseJSONRenderer]
    parser_classes = [CamelCaseJSONParser]

    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [IsAuthenticated(), IsAdminUser()]
        return [AllowAny()]

    @extend_schema(
        responses={200: MaintenanceBannerResponseSerializer},
        description="Returns the current maintenance banner configuration. No authentication required.",
    )
    def get(self, request):
        from core.models import MaintenanceBanner
        banner = MaintenanceBanner.load()
        return Response({
            'active': banner.active,
            'active_now': banner.is_active_now(),
            'message': banner.message,
            'color': banner.color,
            'severity': banner.severity,
            'starts_at': banner.starts_at.isoformat() if banner.starts_at else None,
            'ends_at': banner.ends_at.isoformat() if banner.ends_at else None,
        })

    @extend_schema(
        request=MaintenanceBannerSerializer,
        responses={200: MaintenanceBannerResponseSerializer},
        description="Update the maintenance banner. Requires admin authentication.",
    )
    def patch(self, request):
        from core.models import MaintenanceBanner
        serializer = MaintenanceBannerSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        banner = MaintenanceBanner.load()
        for field, value in serializer.validated_data.items():
            setattr(banner, field, value)
        banner.pk = 1  # enforce singleton
        banner.save()
        return Response({
            'active': banner.active,
            'active_now': banner.is_active_now(),
            'message': banner.message,
            'color': banner.color,
            'severity': banner.severity,
            'starts_at': banner.starts_at.isoformat() if banner.starts_at else None,
            'ends_at': banner.ends_at.isoformat() if banner.ends_at else None,
        })

