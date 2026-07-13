# codePost API — Agent Guidelines

## Architecture

Django 6 + DRF REST API serving the codePost platform. The `core/` app holds all domain models, views, serializers, and permissions. `autograder/` handles sandboxed code execution via Docker + Celery. `webhooks/` delivers async event hooks. `log/` stores audit events.

- **Models**: Single monolithic `core/models.py` — all inherit from `BaseModel` (auto `created`/`modified` timestamps, field change tracking).
- **Views**: One ViewSet per file in `core/views/`, inheriting `ListProtectedViewSet` or `SuperUserListProtectedViewSet`. Sub-resources use `@action`.
- **Serializers**: One per file in `core/serializers/`, inheriting `ModelSerializerWithPOSTCheck` (supports `createForPOSTCheck()` for pre-permission validation).
- **Permissions**: `core/permissions/` — `TemplatePermission` base validates POST data via serializer before `has_object_permission`. Helpers: `isStudent()`, `isGrader()`, `isCourseAdmin()`, `isCourseMember()`, `isStaffOfSub()`, etc.
- **URL routing**: Central `DefaultRouter` in `codepost/urls.py`. Autograder has a separate router.

## Code Style

- Every file must start with: `# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.`
- camelCase for serializer field names and API responses (uses `djangorestframework-camel-case`); snake_case for Python internals.
- Type checking: Pyright `basic` mode. Migrations, `.venv`, and `node_modules` are excluded.
- Use `@extend_schema` / `@extend_schema_field` from `drf_spectacular` for all new endpoints.
- No auto-formatter is enforced — match the style of surrounding code.

## Build and Test

```bash
# Setup
poetry install
python manage.py migrate

# Run dev server (SQLite, eager Celery)
./start_dev.sh              # uvicorn --reload on :8000
./start_dev.sh --local      # force local shell mode (no Redis)
./start_dev.sh --env        # load .env for MySQL/Redis config

# Tests
pytest                      # all tests
pytest core/tests/          # core app tests only
pytest autograder/tests/    # autograder tests only

# Generate OpenAPI schema
.venv/bin/python manage.py spectacular --file schema.yaml

# Regenerate TypeScript client for codePost-ui (run from this repo)
./scripts/generate_ts_client.sh
```

## Project Conventions

- **Adding a new resource**: Create files in `core/views/<resource>.py`, `core/serializers/<resource>.py`, `core/permissions/` (if needed), register ViewSet in `codepost/urls.py` router, add migration.
- **Permissions pattern**: New permissions inherit `TemplatePermission`. Override `has_permission` and `has_object_permission`. Use helper functions from `core/permissions/helpers.py`.
- **Factories for tests**: Define in `core/tests/factories.py` using `factory.django.DjangoModelFactory`. Mute `post_save` signals with `@factory.django.mute_signals` — critical because signals trigger Celery tasks and extra DB work.
- **Test style**: Extend `rest_framework.test.APITestCase`, use `self.client.force_authenticate(user=...)`, hit actual API endpoints, assert status codes + response data.
- **Celery tasks**: Define in `tasks.py` within each app. Dev mode runs with `CELERY_TASK_ALWAYS_EAGER=TRUE`. Import tasks inside signal handlers to avoid circular imports.
- **Services layer**: Complex business logic goes in `core/services/` or `autograder/services/`, not in views.
- **Emails**: Inherit from `CodepostEmail` in `core/emails.py`. Emails are silently skipped when `TESTING=True`. Respect org-level `send_welcome_email` flag.

## Important Gotchas

- **BaseModel extra query**: Every `save()` on an existing object fires an extra `SELECT` to compute changed fields (for `update_fields` optimization). Be aware of this cost in bulk operations.
- **List endpoints are blocked**: `ListProtectedViewSet.list()` returns 403 for non-superusers. Users access resources via parent object actions (e.g., assignments through `courses/{id}/assignments/`), not by listing directly.
- **Archived courses block edits**: `ModelSerializerWithPOSTCheck.validate()` raises `ValidationError` for any model attached to an archived `Course`. The `Course` model itself is exempt.
- **No global pagination**: Regular users access resources via parent actions (e.g., `courses/{id}/assignments/`) which return bounded result sets. Only superuser list endpoints use `ListPagination` (50 per page). For new endpoints needing pagination, add `pagination_class = ListPagination` per-ViewSet.
- **Schema hooks are critical**: `codepost/schema_hooks.py` has `restore_underscore_operation_ids` which restores `tag_action` format in operationIds. Without it, the generated TS client method names break. Must stay in sync with any new tags.
- **`ENUM_NAME_OVERRIDES` match on value+label pairs**: an entry in `codepost/settings.py`'s `ENUM_NAME_OVERRIDES` only applies when its `(value, label)` tuples **exactly** match the model field's `choices` — labels included, not just values. Editing a choice's label (or adding a choice) without updating the matching override silently drops the override, so drf-spectacular auto-names the enum (e.g. `QuizAssignmentTriggerEnum` → `AssignmentTriggerEnum`) and the regenerated TS client breaks `tsc`. When you change a `choices` list, update its `ENUM_NAME_OVERRIDES` entry in lockstep, then regenerate and confirm the enum name is unchanged.
- **Signal side-effects**: `auto_execute_submission` includes a 1-second `time.sleep()`. `auto_detect_on_file_change` fires on `AssignmentFile` save/delete. Always mute signals in test factories.
- **`copy_assignment` uses `update_or_create`** for Environment because the `AssignmentFile` `post_save` signal may have already auto-created one via the `Autodetector`.

## Integration Points

- **Frontend (codePost-ui)**: Consumes this API. Schema changes require regenerating the TS client via `./scripts/generate_ts_client.sh` which outputs to `../codePost-ui/src/api-client/`.
- **Python SDK (codepost-python)**: Generated from the same `schema.yaml` via `./scripts/generate_sdk.sh`.
- **TypeScript SDK (codePost/)**: Separate SDK package also consuming this schema.
- **Database**: MySQL in production (`DB_HOSTNAME` env var), SQLite in dev/test (no env var).
- **Redis**: Celery broker, Channels layer, worker shell relay. Optional in dev (falls back to local mode).
- **S3**: File storage via boto3 when `AWS_STORAGE_BUCKET_NAME` is set.
- **Docker**: Autograder spawns sandboxed containers for code execution.

## Security

- Sensitive fields use `django-encrypted-model-fields` (`EncryptedCharField`).
- Auth: `TokenAuthentication`, `JWTAuthentication` (SimpleJWT sliding tokens), `BasicAuthentication`, `SessionAuthentication`.
- `FIELD_ENCRYPTION_KEY` env var required for encrypted fields.
- `/impersonate/` is a production endpoint — staff/superusers can impersonate any user; course admins can only impersonate students/graders in their courses. It issues a fresh JWT and logs the event.
- `dev-auth/login-as/` is DEBUG-only — not available in production.
- All permission checks must happen in the permission class, not in the view body.
- `DEFAULT_PERMISSION_CLASSES` is `[IsAuthenticated]` — all endpoints require auth unless explicitly overridden.
