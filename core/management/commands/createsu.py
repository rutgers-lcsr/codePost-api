from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    def handle(self, *args, **options):
        if not User.objects.filter(username="james@codepost.io").exists():
            james = User.objects.create_superuser(username="james@codepost.io", email="james@codepost.io", password='rootabega')
            james.save()
        if not User.objects.filter(username="vinay@codepost.io").exists():
            vinay = User.objects.create_superuser(username="vinay@codepost.io", email="vinay@codepost.io", password='rootabega')
            vinay.save()
        # Make regular user test_user
        if not User.objects.filter(username="test_user").exists():
            test_user = User.objects.create_user(username="test_user", email="test_user@codepost.io", password='rootabega')
            test_user.save()
            