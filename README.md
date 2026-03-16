# codePost API

This repository contains the backend API for [codePost](https://codepost.cs.rutgers.edu), built with Django.

## Changelog

- See [`CHANGELOG.md`](./CHANGELOG.md) for recent API changes and release notes.

## Branching & Versioning

### Branches

| Branch        | Purpose                                                                                                             |
| ------------- | ------------------------------------------------------------------------------------------------------------------- |
| `development` | Default branch. All feature work and PRs target here. Pushes auto-deploy to the dev server.                         |
| `master`      | Production branch. Only receives merges from `release/*` and `hotfix/*` branches. Pushes auto-deploy to production. |
| `release/*`   | Cut from `development` when ready to release. Merged into `master` then backmerged to `development`.                |
| `hotfix/*`    | Cut from `master` for urgent production fixes. Merged into `master` then backmerged to `development`.               |

### Versioning

Versioning is fully automated via [python-semantic-release](https://python-semantic-release.readthedocs.io/) and [Conventional Commits](https://www.conventionalcommits.org/).

- **You never manually edit the version** in `pyproject.toml` — semantic-release handles it.
- When a `feat:` or `fix:` commit merges into `master`, the release workflow automatically:
    1. Determines the next semver version from commit messages
    2. Bumps the version in `pyproject.toml`
    3. Updates `CHANGELOG.md`
    4. Creates a git tag (`v3.2.1`, `v3.3.0`, etc.)
    5. Creates a GitHub Release
    6. Triggers SDK regeneration in `codePost-ui` and `codepost-python`

### Commit Message Format

All commits must follow the [Conventional Commits](https://www.conventionalcommits.org/) format. This is enforced by CI on pull requests.

```
feat: add new rubric export endpoint      → minor bump (3.2.0 → 3.3.0)
fix: correct permission check on courses  → patch bump (3.2.0 → 3.2.1)
feat!: redesign submission model           → major bump (3.2.0 → 4.0.0)
chore: update dependencies                 → no release
docs: update API documentation             → no release
```

### Workflows

| Workflow                 | Trigger                                                     | What it does                                  |
| ------------------------ | ----------------------------------------------------------- | --------------------------------------------- |
| `test_codepost.yml`      | Push/PR to `development`, `master`, `release/*`, `hotfix/*` | Lint, typecheck, tests                        |
| `release.yml`            | Push to `master`                                            | Auto-tag, changelog, GitHub Release, SDK sync |
| `deploy_production.yml`  | Push to `master`                                            | Deploy to production servers                  |
| `deploy_development.yml` | Push to `development`                                       | Deploy to dev server                          |
| `release-branch.yml`     | Manual trigger                                              | Create `release/*` branch from `development`  |
| `hotfix-open.yml`        | Manual trigger                                              | Create `hotfix/*` branch from `master`        |
| `hotfix-backmerge.yml`   | Hotfix/release PR merged to `master`                        | Auto-create backmerge PR to `development`     |

### Releasing

1. Go to **Actions → Create Release Branch** → Run workflow (optionally specify version)
2. A `release/X.Y.Z` branch is created and a PR opened targeting `master`
3. Do final testing on the release branch
4. Merge the PR — everything else is automatic

### Hotfixing Production

1. Go to **Actions → Open Hotfix Branch** → Run workflow with a description
2. A `hotfix/X.Y.Z` branch is created and a draft PR opened targeting `master`
3. Push your fix to the hotfix branch
4. Merge the PR — deployment, tagging, and backmerge to `development` are automatic

This README documents the **current production deployment flow** used for codePost with a multi-VM layout and `docker-compose`.

## What this repository deploys

Primary services in this repo:

- `codepost-api`: Django API service
- `codepost-entry`: Nginx TLS reverse proxy for API
- `codepost-worker`: Celery worker for background jobs/autograding
- `codepost-worker-shell`: worker-shell relay process
- `codepost-database`: MariaDB
- `codepost-redis`: Redis

Optional operational services:

- `codepost-flower`: Celery monitoring UI
- `adminer`: database web UI

## Production deployment (multi-VM)

### End-to-end setup (from git clone to full deployment)

This is the fastest path for a new operator starting from zero.

#### 0) Prepare host machines

Provision these VMs:

- Data VM
- Backend VM
- Worker VM
- Frontend VM

Install on each VM:

- Git
- Docker Engine
- Docker Compose plugin (`docker-compose` command)
- Python 3 (for env generation script)

Also ensure:

- VM-to-VM connectivity is open for required ports (DB/Redis/API)
- DNS records are configured for API and frontend domains

#### 1) Clone repositories

On Data, Backend, and Worker VMs:

```bash
git clone https://github.com/rutgers-lcsr/codePost-api.git
cd codePost-api
```

On Frontend VM:

```bash
git clone https://github.com/rutgers-lcsr/codePost-ui.git
cd codePost-ui
```

#### 2) Create and distribute API `.env`

Create `.env` once in `codePost-api/` (for example on Backend VM):

```bash
python3 ./scripts/create_env.py
```

Then copy the same `.env` to Data VM and Worker VM in their `codePost-api/` folders.

Important values to confirm before deploy:

- `DB_HOSTNAME` points to the Data VM host
- `API_URL` is your external API URL (example: `https://api.example.edu`)
- `CLIENT_URL` is your frontend URL (example: `https://codepost.example.edu`)
- `WORKER_SHELL_SHARED_SECRET` is identical on Backend + Worker
- `NFS_*` values are set correctly if NFS-backed DB volume is enabled

#### 3) Prepare API TLS certs (Backend VM)

In `codePost-api/`, place cert files:

- `certs/fullchain.pem`
- `certs/privkey.pem`

#### 4) Create frontend `.env` (Frontend VM)

In `codePost-ui/`, create `.env` with:

```ini
REACT_APP_API_URL=https://api.yourdomain.com
```

#### 5) Prepare frontend TLS certs (Frontend VM)

In `codePost-ui/`, place cert files:

- `certs/fullchain.pem`
- `certs/privkey.pem`

#### 6) Deploy in order

On Data VM (`codePost-api/`):

```bash
docker-compose --env-file .env -f docker-compose-data.yml up -d
```

On Backend VM (`codePost-api/`):

```bash
docker-compose --env-file .env -f docker-compose-prod.yml up -d --build
```

On Worker VM (`codePost-api/`):

```bash
docker-compose --env-file .env -f docker-compose-worker.yml up -d --build
```

On Frontend VM (`codePost-ui/`):

```bash
docker-compose --env-file .env -f docker-compose.yml up -d --build
```

#### 7) Verify deployment

- API health check: `https://<api-domain>/health-check`
- Frontend loads over HTTPS
- Login succeeds in UI
- Background jobs run successfully on worker

#### 8) First admin setup

- `init.sh` auto-creates admin user from `API_USER` / `API_PASSWORD`
- Open Django admin at `https://<api-domain>/admin/`
- Create Organization and link your profile

Current recommended topology:

- **Data VM**: `docker-compose-data.yml`
- **Backend VM**: `docker-compose-prod.yml`
- **Worker VM**: `docker-compose-worker.yml`
- **Frontend VM**: deployed from `codePost-ui` (see [README](https://github.com/rutgers-lcsr/codePost-ui/blob/master/README.md))

### Deployment order

Use this order for first deploy and most restarts:

1. Data VM
2. Backend VM
3. Worker VM
4. Frontend VM

### Prerequisites

- Docker + Docker Compose plugin installed
- DNS / routing configured so VMs can reach each other
- TLS certificates available on API and UI hosts
- Host paths created where required:
    - `HOST_DATASET_ROOT` (default `/mnt/datasets`)
    - `/tmp/codepost-staging`

### Environment variables (`.env`)

Create a `.env` file in `codePost-api/` using one of the following:

```bash
# Interactive (recommended)
python3 ./scripts/create_env.py

# Non-interactive defaults/placeholders
python3 ./scripts/create_env.py --non-interactive

# Backward-compatible wrapper still works
./scripts/create_env.sh
```

The interactive flow will ask whether optional features should be activated (for example, NFS-backed DB volume and autograder auto-execution).

Or copy `.env.example` manually and edit values.

Required (or strongly recommended) fields for production:

```ini
DEBUG=False

SECRET_KEY=<secure_random_string>
FIELD_ENCRYPTION_KEY=<secure_random_key>

DB_HOSTNAME=<hostname_or_ip_of_data_vm_database_and_redis>
DB_NAME=codepost
DB_PASSWORD=<db_password>
ROOT_DATABASE_PASSWORD=<db_root_password>

API_USER=<initial_admin_username>
API_PASSWORD=<initial_admin_password>

API_URL=https://api.yourdomain.com
CLIENT_URL=https://yourdomain.com

EMAIL_HOST=<smtp_host>
DEFAULT_EMAIL_FROM=<noreply@yourdomain.com>

CELERY_CONCURRENCY=4
HOST_DATASET_ROOT=/mnt/datasets

WORKER_SHELL_SHARED_SECRET=<shared_secret_used_by_api_and_worker>
WORKER_SHELL_REDIS_URL=redis://<data-vm-host>:6379
WORKER_SHELL_WORKER_ID=<optional_worker_id>

# Required when using NFS-backed database volume in docker-compose-data.yml
NFS_SERVER_IP=<nfs_server_ip>
NFS_SHARE_PATH=<nfs_export_path>
```

Notes:

- Compose files set `DB_USERNAME=codepost_user` internally.
- `.env.example` includes `DB_USER`; this variable is retained for compatibility but is not used by the current compose runtime.
- `DB_HOSTNAME` is also used for Redis URLs in current compose files.

### Step 1: Data VM

On the Data VM, from `codePost-api/`:

```bash
docker-compose --env-file .env -f docker-compose-data.yml up -d
```

This starts MariaDB + Redis and optional operations services (`codepost-flower`, `adminer`).

### Step 2: Backend VM

On the Backend VM, from `codePost-api/`:

```bash
docker-compose --env-file .env -f docker-compose-prod.yml up -d --build
```

This starts API + Nginx entry service.

### Step 3: Worker VM

On the Worker VM, from `codePost-api/`:

```bash
docker-compose --env-file .env -f docker-compose-worker.yml up -d --build
```

This starts Celery worker + worker-shell relay.

### Step 4: Frontend VM

Deploy UI from `codePost-ui` using its README (`../codePost-ui/README.md`).

## TLS certificates

`codepost-entry` expects cert files mounted from `./certs`:

- `./certs/fullchain.pem`
- `./certs/privkey.pem`

These map to:

- `/etc/ssl/certs/fullchain.pem`
- `/etc/ssl/certs/privkey.pem`

## Initialization behavior (`init.sh`)

At startup, API containers run `init.sh`, which:

1. runs migrations (`python manage.py migrate --noinput`)
2. creates/updates the API admin user from `API_USER` and `API_PASSWORD`
3. prints/creates API token for that user

## Verification checklist

After deploy:

- Data VM: DB and Redis containers healthy
- Backend VM: `https://<api-domain>/health-check` reachable
- Worker VM: worker containers running and stable
- Frontend VM: UI loads and can make authenticated API requests

## Development setup

For local development:

1. `pip install poetry && poetry install`
2. `python manage.py migrate`
3. `./init.sh python manage.py runserver`

## Manual user creation

Create interactive superuser:

```bash
docker-compose -f docker-compose-prod.yml exec codepost-api python manage.py createsuperuser
```

Legacy helper for default development users:

```bash
docker-compose -f docker-compose-prod.yml exec codepost-api python manage.py createsu
```

## Organization setup

After admin user creation:

1. Open Django admin (`/admin/`)
2. Create an Organization under `Core > Organizations`
3. Link your user profile under `Core > Profiles`
4. Enable needed permissions (`CanCreateCourses`, `CanModifyRosters`)

## License

This repository is licensed under the Rutgers Non-commercial License (RU-NCL).

See [`LICENSE`](./LICENSE) for the full terms.

## Internal/legacy deployment notes

Alternative deployment files (including platform-specific configurations) are maintained separately from this public quickstart.
