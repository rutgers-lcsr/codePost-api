FROM python:3.12 AS api

WORKDIR /opt/app

COPY pyproject.toml poetry.lock* /opt/app/


RUN pip install poetry
RUN poetry config virtualenvs.create false \
 && poetry install --no-root

COPY . .

RUN python manage.py collectstatic --no-input

RUN chmod +x init.sh

CMD ["/opt/app/init.sh", "gunicorn", "--workers=4", "--threads=16",  "codepost.wsgi:application", "--bind", "0.0.0.0:8000"]

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

CMD [ "celery", "--app", "autograder", "worker", "--loglevel", "info", "--concurrency", "4", "--task-events"]

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

# CHANGE THIS FOR DEPLOYMENT
CMD ["celery", "--app", "autograder", "flower", "--basic-auth=${API_USER}:${API_PASSWORD}"]
