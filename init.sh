#!/bin/bash
# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
set -e

# Before we run migrations, make sure we can migrate safely
# This script checks for any potential issues that could cause the migration to fail
# such as missing files, permission issues, or database connectivity problems.
# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi


# Run migrations
python manage.py migrate --noinput



python manage.py shell <<EOF
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.db import OperationalError

try:
    username = "${API_USER}"
    email = "${API_USER}" + "@example.com"
    password = "${API_PASSWORD}"

    if not User.objects.filter(username=username).exists():
        user = User.objects.create_user(username=username, email=email,  password=password)
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
EOF

exec "$@"
