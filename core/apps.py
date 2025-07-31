from django.apps import AppConfig

from .logging import loki_handler, logEvent

class CoreConfig(AppConfig):
    name = 'core'
    
    def ready(self):
        logEvent("Core App Ready", message="Core app has been initialized and logging handler added.")