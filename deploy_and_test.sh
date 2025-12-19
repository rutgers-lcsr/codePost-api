#!/bin/bash
set -e

echo "--- Deploying Test Stack ---"
docker compose -f docker-compose-test.yml down -v --remove-orphans
docker compose -f docker-compose-test.yml up -d --build --remove-orphans

echo "--- Waiting for Services ---"
sleep 15 # Give DB time to init

echo "--- Running Migrations ---"
docker exec codepost-api-test python manage.py migrate

echo "--- Creating Admin User ---"
# Check if exists first to avoid error, or just try catch
docker exec codepost-api-test python manage.py shell -c "from django.contrib.auth.models import User; User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'admin@example.com', 'admin_password')"

echo "--- Running Verification Script ---"
# Install requests if missing (should be there)
pip install requests > /dev/null 2>&1 || true

export API_URL="http://localhost:8001"
# Allow validation failure
set +e
python3 verify_docker.py
EXIT_CODE=$?
set -e

echo "--- Clean Up? (Leaving running for debug if failed, else down) ---"
if [ $EXIT_CODE -eq 0 ]; then
    echo "SUCCESS! Tearing down..."
    docker compose -f docker-compose-test.yml down -v
else
    echo "FAILURE! Leaving stack up for inspection."
    echo "To clean up run: docker compose -f docker-compose-test.yml down -v"
fi

exit $EXIT_CODE
