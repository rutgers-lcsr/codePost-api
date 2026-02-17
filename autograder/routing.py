from django.urls import re_path

from autograder.consumers import EnvironmentShellConsumer, WorkerShellConsumer

websocket_urlpatterns = [
    re_path(r"ws/autograder/environments/(?P<environment_id>\d+)/shell/$", EnvironmentShellConsumer.as_asgi()),  # type: ignore[arg-type]
    re_path(
        r"ws/internal/autograder/environments/(?P<environment_id>\d+)/shell/$",
        WorkerShellConsumer.as_asgi(),  # type: ignore[arg-type]
    ),
]
