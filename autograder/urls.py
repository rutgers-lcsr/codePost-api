# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.http import HttpResponse
from django.urls import path, re_path, include


from autograder.views.environment import EnvironmentViewSet


from autograder.views.TaskViewset import TaskViewSet
from autograder.views.executor_streaming import ExecuteFileStreaming
from autograder.views.executor_async import ExecuteFileAsyncView
from autograder.views.cache_check import CheckExecutionCache
from autograder.views.test_execution import RunTestView
from autograder.views.environment_actions import (
    EnvironmentRollback,
    EnvironmentCleanup,
    EnvironmentConvertToManual,
    EnvironmentStatus,
)
from autograder.views.environment_shell import ShellMetricsView

from rest_framework import routers
def health_check(request):
    return HttpResponse(status=200)
router = routers.DefaultRouter()
router.register(r"environments", EnvironmentViewSet)


urlpatterns = [
    path(r"tasks/<str:pk>/", TaskViewSet.as_view({"get": "retrieve"})),
    path(r"execute/file/streaming/", ExecuteFileStreaming.as_view(), name="execute-file-streaming"),
    path(r"execute/file/async/", ExecuteFileAsyncView.as_view(), name="execute-file-async"),
    path(r"execute/file/cache/check/", CheckExecutionCache.as_view(), name="check-execution-cache"),
    path(r"v2/run/", RunTestView.as_view(), name="run-test"),
    path("health/", health_check, name="health-check"),
    
    # Admin environment actions
    path(r"environments/<int:environment_id>/rollback/", EnvironmentRollback.as_view(), name="environment-rollback"),
    path(r"environments/<int:environment_id>/cleanup/", EnvironmentCleanup.as_view(), name="environment-cleanup"),
    path(r"environments/<int:environment_id>/convert-to-manual/", EnvironmentConvertToManual.as_view(), name="environment-convert-manual"),
    path(r"environments/<int:environment_id>/status/", EnvironmentStatus.as_view(), name="environment-status"),

    # Shell metrics
    path(r"shell/metrics/", ShellMetricsView.as_view(), name="shell-metrics"),
    
    re_path("", include(router.urls)),
]

