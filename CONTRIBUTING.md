# Contributing to codePost-api

Thanks for your interest in contributing. codePost is the Rutgers-CS code-review and autograding platform; this repository is the Django + DRF backend.

For ecosystem-wide setup (running api + ui + sdk together), see the hub repo: <https://github.com/rutgers-lcsr/codePost/blob/main/CONTRIBUTING.md>.

This file covers backend-specific workflow.

## License

This project is source-available under the [Rutgers Non-Commercial License](./LICENSE). Contributions are accepted under the same terms. Every new source file must begin with:

```
# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
```

## Local setup

```bash
poetry install
python manage.py migrate
./start_dev.sh                  # uvicorn --reload on :8000
./start_dev.sh --local          # force local shell mode (no Redis)
./start_dev.sh --env            # load .env for MySQL/Redis config
```

## Tests

```bash
pytest                          # all tests
pytest core/tests/              # core app tests only
pytest autograder/tests/        # autograder tests only
```

Test guidelines (see [AGENTS.md](./AGENTS.md) for the full conventions):

- Extend `rest_framework.test.APITestCase`.
- Use factories in `core/tests/factories.py` and **always** mute `post_save` signals on factories — they trigger Celery tasks and extra DB work.
- Hit real API endpoints with `self.client.force_authenticate(user=...)`.

## Pull requests

- Branch from `main`. Keep PRs focused — one concern per PR.
- Run `pytest` and confirm it passes locally before pushing.
- If you touch the schema, regenerate the TypeScript client (`./scripts/generate_ts_client.sh`) and the Python SDK (`./scripts/generate_sdk.sh`) and include the regenerated output in a separate commit.
- Add `@extend_schema` / `@extend_schema_field` from `drf_spectacular` for any new endpoint.

## Architecture quick reference

The full architectural overview lives in [AGENTS.md](./AGENTS.md). The short version:

- Domain models: monolithic `core/models.py`, all inherit `BaseModel`.
- ViewSets: one per file in `core/views/`, inheriting `ListProtectedViewSet` or `SuperUserListProtectedViewSet`.
- Serializers: one per file in `core/serializers/`, inheriting `ModelSerializerWithPOSTCheck`.
- Permissions: `core/permissions/`, base class `TemplatePermission`.
- Autograder: sandboxed code execution via Docker + Celery in `autograder/`.

## Reporting bugs

Use GitHub Issues for bugs and feature requests. For security vulnerabilities, follow [SECURITY.md](./SECURITY.md) instead.

## Code of Conduct

This project follows the [Contributor Covenant](./CODE_OF_CONDUCT.md). By participating, you agree to abide by its terms.
