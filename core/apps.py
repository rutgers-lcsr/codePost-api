from django.apps import AppConfig

# from .logging import loki_handler

class CoreConfig(AppConfig):
    name = 'core'
    
    def ready(self):
        pass

        # logEvent("Core App Ready", message="Core app has been initialized and logging handler added.")