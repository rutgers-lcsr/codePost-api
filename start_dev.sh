#!/bin/bash

export DEBUG=TRUE
export AUTOGRADER_AUTO_EXECUTE=TRUE
export CELERY_TASK_ALWAYS_EAGER=TRUE

source .venv/bin/activate
python manage.py runserver