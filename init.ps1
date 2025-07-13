# Requires PowerShell 7+ for heredoc support

$ErrorActionPreference = "Stop"

# Run migrations
python manage.py migrate --noinput

# Prepare the Python script for user creation
$pythonScript = @"
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.db import OperationalError

try:
    username = "${env:API_USER}"
    email = f"{username}@example.com"
    password = "${env:API_PASSWORD}"

    if not User.objects.filter(username=username).exists():
        user = User.objects.create_user(username=username, email=email, password=password)
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        token, _ = Token.objects.get_or_create(user=user)
        print(f"Created API user: {username}")
        print("API Token:", token.key)
    else:
        user = User.objects.get(username=username)
        token, _ = Token.objects.get_or_create(user=user)
        print("API user already exists")
        print("API Token:", token.key)
except OperationalError:
    print("❌ Database tables are not ready yet!")
"@

# Run the Python script in Django shell
python manage.py shell "$pythonScript"

# Execute any additional arguments passed to the script
if ($args.Count -gt 0) {
    & $args
}