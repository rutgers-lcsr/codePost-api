from django.urls import path, re_path, include

import core.views.logging as logging

urlpatterns = [
  path('logError/', logging.logError),
  path('logHappiness/', logging.logHappiness),
  path('log/', logging.logDump),
]
