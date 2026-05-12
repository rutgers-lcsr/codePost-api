# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.urls import path

import core.views.logging as logging

urlpatterns = [
  path('logError/', logging.logError),
  path('logHappiness/', logging.logHappiness),
  path('log/', logging.logDump),
]
