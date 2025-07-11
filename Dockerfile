FROM python:3.8 AS api




COPY pyproject.toml poetry.lock* /opt/app/
WORKDIR /opt/app


RUN pip install poetry
RUN poetry config virtualenvs.create false \
 && poetry install --no-root --no-dev

COPY . .

RUN python manage.py collectstatic --no-input
RUN python manage.py migrate



CMD ["gunicorn", "--workers=4", "--threads=16",  "codepost.wsgi:application"]

FROM python:3.8 AS worker

COPY --from=api /opt/app /opt/app
WORKDIR /opt/app    


COPY pyproject.toml poetry.lock* /opt/app/
WORKDIR /opt/app


RUN pip install poetry
RUN poetry config virtualenvs.create false \
 && poetry install --no-root --no-dev

RUN pip install celery 

COPY . .

RUN python manage.py collectstatic --no-input
RUN python manage.py migrate



CMD [ "celery", "--app", "autograder", "worker", "--loglevel", "info", "--concurrency", "4", "--task-events"]

FROM python:3.8 AS flower
COPY --from=api /opt/app /opt/app
WORKDIR /opt/app


COPY pyproject.toml poetry.lock* /opt/app/
WORKDIR /opt/app


RUN pip install poetry
RUN poetry config virtualenvs.create false \
 && poetry install --no-root --no-dev
RUN pip install celery 

COPY . .

# CHANGE THIS FOR DEPLOYMENT
CMD ["celery", "--app", "autograder", "flower", "--basic-auth=richard:fruitabega"]