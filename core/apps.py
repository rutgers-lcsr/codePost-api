# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.apps import AppConfig

# from .logging import loki_handler

class CoreConfig(AppConfig):
    name = 'core'
    
    def ready(self):
        # Import signals to connect them
        import core.signals  # noqa: F401

        # OAuth consent/DCR audit trail (log.Event; course-agnostic)
        from core.oauth_audit import register_oauth_audit_receivers
        register_oauth_audit_receivers()
        
        # logEvent("Core App Ready", message="Core app has been initialized and logging handler added.")