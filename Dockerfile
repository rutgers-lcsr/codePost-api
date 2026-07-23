FROM python:3.12 AS api

WORKDIR /opt/app

COPY pyproject.toml poetry.lock* /opt/app/


RUN pip install poetry
# Install from the committed poetry.lock — don't delete it, or builds float to the newest
# releases on PyPI and can break with no change on our side.
RUN poetry config virtualenvs.create false \
    && poetry install --no-root

COPY . .

# Skip stray node_modules bundled in package static dirs (viewflow); their CSS references
# fonts they don't ship, which fails the manifest storage's strict post-processing.
RUN python manage.py collectstatic --no-input --ignore node_modules

RUN chmod +x init.sh

# API runs as root — requires Docker socket access and write access to NFS-mounted volumes
CMD ["/opt/app/init.sh", "gunicorn", "--workers=4", "--worker-class", "uvicorn.workers.UvicornWorker", "codepost.asgi:application", "--bind", "0.0.0.0:8000"]

FROM python:3.12 AS worker

COPY --from=api /opt/app /opt/app
WORKDIR /opt/app


COPY pyproject.toml poetry.lock* /opt/app/
WORKDIR /opt/app


RUN pip install poetry
RUN poetry config virtualenvs.create false \
    && poetry install --no-root

RUN pip install celery

COPY . .

# Worker runs as root — requires Docker socket access for autograder containers
CMD ["sh", "-c", "celery --app autograder worker --loglevel info --concurrency ${CELERY_CONCURRENCY:-4} --task-events"]

FROM python:3.12 AS flower
COPY --from=api /opt/app /opt/app
WORKDIR /opt/app


COPY pyproject.toml poetry.lock* /opt/app/
WORKDIR /opt/app


RUN pip install poetry
RUN poetry config virtualenvs.create false \
    && poetry install --no-root
RUN pip install celery

COPY . .

RUN adduser --disabled-password --no-create-home --gecos '' appuser
USER appuser

CMD ["celery", "--app", "autograder", "flower"]
