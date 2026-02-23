# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.apps import AppConfig


class AutograderConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'autograder'

    def ready(self):
        import autograder.tasks

