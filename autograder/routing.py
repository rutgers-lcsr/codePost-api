# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import re_path

from autograder.consumers import EnvironmentShellConsumer, WorkerShellConsumer

websocket_urlpatterns = [
    re_path(r"ws/autograder/environments/(?P<environment_id>\d+)/shell/$", EnvironmentShellConsumer.as_asgi()),  # type: ignore[arg-type]
    re_path(
        r"ws/internal/autograder/environments/(?P<environment_id>\d+)/shell/$",
        WorkerShellConsumer.as_asgi(),  # type: ignore[arg-type]
    ),
]
