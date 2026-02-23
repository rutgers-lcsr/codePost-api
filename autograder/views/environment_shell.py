# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Instructor shell access for environment debugging.

Provides endpoints to create a short-lived container session based on an
assignment's environment image, execute shell commands inside it, and stop it.
"""

import json
import logging
from typing import Any, List, Optional, Set, cast

import redis
from django.conf import settings
from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import GenericAPIView
from drf_spectacular.utils import extend_schema
from autograder.serializers.execution import ShellMetricsResponseSerializer

logger = logging.getLogger(__name__)

METRICS_ACTIVE_KEY = "shell:metrics:active"
METRICS_IN_KEY = "shell:metrics:in"
METRICS_OUT_KEY = "shell:metrics:out"
METRICS_SESSIONS_KEY = "shell:metrics:sessions"
METRICS_LAST_ACTIVITY_PREFIX = "shell:metrics:last_activity:"




def _get_redis_url() -> str:
    return (
        getattr(settings, "WORKER_SHELL_REDIS_URL", "")
        or getattr(settings, "CELERY_BROKER_URL", "")
        or "redis://localhost:6379"
    )


def _get_metrics_redis_client() -> redis.Redis:
    return redis.Redis.from_url(_get_redis_url(), decode_responses=True)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


class ShellMetricsView(GenericAPIView):
    """
    Staff-only shell relay metrics from Redis.
    GET /autograder/shell/metrics/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ShellMetricsResponseSerializer

    @extend_schema(responses={200: ShellMetricsResponseSerializer})
    def get(self, request):
        if not (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False) or settings.DEBUG):
            return JsonResponse({"error": "Staff access required"}, status=403)

        client = _get_metrics_redis_client()
        try:
            active_ids = list(cast(Set[str], client.smembers(METRICS_ACTIVE_KEY)))
            in_count = _safe_int(client.get(METRICS_IN_KEY))
            out_count = _safe_int(client.get(METRICS_OUT_KEY))

            sessions = []
            if active_ids:
                session_data = cast(List[Optional[str]], client.hmget(METRICS_SESSIONS_KEY, active_ids))
                for session_id, raw in zip(active_ids, session_data):
                    info = {}
                    if raw:
                        try:
                            info = json.loads(raw)
                        except Exception:
                            info = {}
                    last_activity = client.get(f"{METRICS_LAST_ACTIVITY_PREFIX}{session_id}")
                    info.update({
                        "sessionId": session_id,
                        "lastActivity": _safe_float(last_activity),
                    })
                    sessions.append(info)

            worker_ids = list(cast(Set[str], client.smembers("shell:workers")))
            worker_count = len(worker_ids)
            payload = {
                "activeCount": len(active_ids),
                "inCount": in_count,
                "outCount": out_count,
                "workerCount": worker_count,
                "workerIds": worker_ids,
                "activeIds": active_ids,
                "redisUrl": _get_redis_url(),
                "sessions": sessions,
            }
            return JsonResponse(payload)
        except Exception as e:
            logger.error(f"Failed to read shell metrics: {e}")
            return JsonResponse({"error": "Failed to read metrics"}, status=500)
