from django.apps import AppConfig

from .logging import loki_handler

class CoreConfig(AppConfig):
    name = 'core'
    
    def ready(self):
        import logging
        logging.getLogger().addHandler(loki_handler)