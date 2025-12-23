import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "autograder.settings")

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Starts a Celery worker for the autograder application."
    
    def add_arguments(self, parser):
        parser.add_argument("--loglevel", default="info", help="Log level")
        parser.add_argument("--concurrency", default=os.environ.get("CELERY_CONCURRENCY", 4), type=int, help="Number of worker processes")
    
    def handle(self, *args, **options):
        from celery import Celery

        app = Celery("autograder")
        app.config_from_object("django.conf:settings", namespace="CELERY")
        app.autodiscover_tasks()

        app.start(
            concurrency=options["concurrency"],
            loglevel=options["loglevel"],
        )