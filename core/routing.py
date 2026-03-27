# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from django.urls import re_path

from core.consumers.chat_consumer import ChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/chat/(?P<submission_id>\d+)/$", ChatConsumer.as_asgi()),  # type: ignore[arg-type]
]
