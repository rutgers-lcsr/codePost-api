# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.test import SimpleTestCase

from autograder.run import BuildEnvironment, RunAll, RunQuizResponseCode, RunSubmission, RunSubmissionVariant


class AutograderTaskReliabilityFlags(SimpleTestCase):
    """Regression net for the worker-loss settings chosen in autograder/run.py."""

    def test_idempotent_time_bounded_tasks_survive_worker_loss(self):
        for task in (RunSubmission, RunSubmissionVariant, RunQuizResponseCode):
            with self.subTest(task=task.name):
                self.assertTrue(task.acks_late)
                self.assertTrue(task.reject_on_worker_lost)
                # kombu redelivers unacked messages after visibility_timeout (3600 s) even
                # while they are still running; a hard limit well below that keeps it safe.
                self.assertLess(task.time_limit, 3600)

    def test_unbounded_tasks_keep_early_ack(self):
        for task in (RunAll, BuildEnvironment):
            with self.subTest(task=task.name):
                self.assertFalse(task.acks_late)
