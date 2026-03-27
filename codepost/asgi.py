# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
ASGI config for codepost project.

Exposes the ASGI callable as a module-level variable named ``application``.
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")

django_asgi_app = get_asgi_application()

# Import routing after Django is initialized to avoid AppRegistryNotReady
import autograder.routing  # noqa: E402
import core.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(
            autograder.routing.websocket_urlpatterns
            + core.routing.websocket_urlpatterns
        ),
    }
)
