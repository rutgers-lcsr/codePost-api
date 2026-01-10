# codePost API & Deployment Guide

This repository contains the backend API for [codePost](https://codepost.cs.rutgers.edu), built with Django. It also serves as the central hub for deploying the full codePost stack (API, Database, Workers, and services) using Docker Compose.

## Prerequisites

-   [Docker](https://docs.docker.com/get-docker/)
-   [Docker Compose](https://docs.docker.com/compose/install/)

## Architecture Overview

The deployment consists of several services orchestrated via Docker Compose:

-   **`codepost-api`**: The main Django application server (Gunicorn).
-   **`codepost-worker`**: Celery worker for asynchronous tasks (autograding, emails).
-   **`codepost-database`**: MariaDB instance for persistent data.
-   **`codepost-redis`**: Redis for caching and Celery message brokering.
-   **`codepost-entry`**: Nginx reverse proxy handling SSL and routing to the API.
-   **`codepost-flower`**: (Optional) Tool for monitoring Celery workers.

## Deployment Steps

### 1. Networking Setup

Ensure you have a Docker network created for the services to communicate. The default configuration uses `codepost-network`.

```bash
docker network create codepost-network
```

### 2. Environment Configuration

Create a `.env` file in the root of the `codePost-api` directory. You can start by copying `.env.example` if it exists, or use the reference below.

**Required `.env` Variables:**

```ini
# Debugging
DEBUG=False

# Security & Encryption
SECRET_KEY=<generate_a_secure_random_string>
FIELD_ENCRYPTION_KEY=<generate_a_secure_key_for_db_encryption>

# Database Configuration
DB_HOSTNAME=codepost-database
DB_NAME=codepost
DB_USER=codepost_user
DB_PASSWORD=<secure_db_password>
ROOT_DATABASE_PASSWORD=<secure_root_password>

# API Admin User (created on startup if not exists)
API_USER=admin_user
API_PASSWORD=<secure_admin_password>

# URLs (Important for CORS and emails)
API_URL=https://api.yourdomain.com
CLIENT_URL=https://yourdomain.com

# Email Settings
EMAIL_HOST=smtp.yourprovider.com
DEFAULT_EMAIL_FROM=no-reply@yourdomain.com

# Celery / Redis
CELERY_CONCURRENCY=4

# Storage Paths (Host) must be mounted to the container for the api and the workers to access them
HOST_DATASET_ROOT=/mnt/datasets
```

### 3. Deploy Core Services (Database & Redis)

Start the persistent storage services first.

```bash
docker-compose -f docker-compose-data.yml up -d
```

### 4. Deploy API & Workers

Once the database is up and healthy, deploy the API and Worker containers.

```bash
# Deploys the API and Nginx entry point
docker-compose -f docker-compose-prod.yml up -d

# Deploys the Celery Worker
docker-compose -f docker-compose-worker.yml up -d
```

### SSL Configuration

 The `codepost-entry` service (Nginx) expects SSL certificates to be present in the `./certs` directory relative to this repository root.

-   Place your full chain certificate at `./certs/fullchain.pem`
-   Place your private key at `./certs/privkey.pem`

## Development Setup

For local development:

1.  Install dependencies: `pip install poetry && poetry install`
2.  Run migration: `python manage.py migrate`
3.  Start server: `./init.sh python manage.py runserver`

## Bootstrapping & Initialization

When the container starts, `init.sh` runs automatically to bootstrap the application:

1.  **Migrations**: It runs `python manage.py migrate` to ensure the database schema is up to date.
2.  **Admin User**: It automatically creates a superuser based on the `API_USER` and `API_PASSWORD` environment variables.
    -   If the user does not exist, it is created.
    -   An API Token is generated and printed to the logs.
    -   This allows you to immediately log in to the admin panel or authenticate via API.

## Manual User Creation

If you need to create additional users manually, you can use the following Django management commands:

### Standard Superuser

To create a new superuser interactively:

```bash
docker compose -f docker-compose-prod.yml exec codepost-api python manage.py createsuperuser
```

### Default Development Users (Legacy)

There is a custom command that creates a set of hardcoded development users (e.g., `james@example.com`, `vinay@example.com` with password `rootabega`):

```bash
docker compose -f docker-compose-prod.yml exec codepost-api python manage.py createsu
```

## Organization Setup

After creating your admin user, you need to set up an **Organization** (e.g., your University).

1.  Log in to the **Django Admin Panel** at `http://localhost:8000/admin/` (or your deployed URL).
2.  Navigate to **Core > Organizations**.
3.  Click **Add Organization** in the top right.
4.  Fill in the required fields:
    *   **Name**: Full name (e.g., `Princeton University`)
    *   **Shortname**: Abbreviation (e.g., `Princeton`) – *Must be unique*
5.  Click **Save**.

### Linking Your User

To associate your admin user with this organization:

1.  Go to **Core > Profiles** in the Admin Panel.
2.  Find your user profile (e.g., `james@example.com`).
3.  Set the **Organization** field to the one you just created.
4.  Ensure **CanCreateCourses** and **CanModifyRosters** are checked if you need full permissions.
5.  Click **Save**.

