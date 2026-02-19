from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.utils.log import get_task_logger

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")

app = Celery("autograder", broker=os.getenv("CELERY_BROKER_URL"))
app.config_from_object("django.conf:settings", namespace="CELERY")

logger = get_task_logger(__name__)

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
