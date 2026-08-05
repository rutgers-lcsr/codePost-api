# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Celery routing invariants for the AI worker split.

Tasks that decrypt EncryptedCharField secrets must land on the 'ai-tasks'
queue — the only queue consumed by a worker that has FIELD_ENCRYPTION_KEY.
These tests exercise the REAL router, not just the settings dict: an invalid
setting name silently no-ops under Celery's namespace handling (the old
CELERY_DEFAULT_QUEUE was inert for exactly that reason), and a task rename
would silently un-route the task back onto the untrusted default queue.
"""
from django.conf import settings
from django.test import TestCase

from autograder.celery import app

AI_TASKS = [
    'core.tasks.generate_ai_grading_assistance',
    'core.tasks.generate_quiz_question_suggestions',
    'core.tasks.generate_personalized_quiz_sets',
    'core.tasks.backfill_personalized_quiz_sets',
    'core.tasks.preview_generated_section',
    'core.tasks.auto_improve_prompts_scheduled',
    'core.tasks.auto_improve_prompt_threshold',
]


class TestAITaskRouting(TestCase):

    def test_routes_declared_in_settings(self):
        for name in AI_TASKS:
            self.assertEqual(settings.CELERY_TASK_ROUTES.get(name), {'queue': 'ai-tasks'}, name)

    def test_routed_names_are_registered_tasks(self):
        """A rename in core/tasks.py must update the route map — an unknown name
        here means the task silently falls back to the keyless default queue."""
        import core.tasks  # noqa: F401 — ensure task registration
        for name in AI_TASKS:
            self.assertIn(name, app.tasks, name)

    def test_router_resolves_ai_queue(self):
        """The live router (what .delay() actually consults) must route to ai-tasks."""
        for name in AI_TASKS:
            route = app.amqp.router.route({}, name)
            self.assertEqual(route['queue'].name, 'ai-tasks', name)

    def test_default_queue_is_celery(self):
        """The compose -Q lists (worker: celery; ai-worker: ai-tasks;
        single-worker stacks: celery,ai-tasks) depend on this default."""
        self.assertEqual(app.conf.task_default_queue, 'celery')

    def test_unrouted_task_stays_on_default_queue(self):
        route = app.amqp.router.route({}, 'core.tasks.import_quiz_qti')
        self.assertEqual(route['queue'].name, 'celery')
