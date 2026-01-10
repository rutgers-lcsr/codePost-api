from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    def handle(self, *args, **options):
        if not User.objects.filter(username="james@example.com").exists():
            james = User.objects.create_superuser(username="james@example.com", email="james@example.com", password='rootabega')
            james.save()
        if not User.objects.filter(username="vinay@example.com").exists():
            vinay = User.objects.create_superuser(username="vinay@example.com", email="vinay@example.com", password='rootabega')
            vinay.save()
        # Make regular user test_user
        if not User.objects.filter(username="test_user").exists():
            test_user = User.objects.create_user(username="test_user", email="test_user@example.com", password='rootabega')
            test_user.save()
            