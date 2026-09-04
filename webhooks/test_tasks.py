# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from unittest import mock

from django.test import SimpleTestCase

from webhooks.tasks import deliver_hook


class DeliverHookTimeoutTests(SimpleTestCase):
    """Webhook delivery is bounded: a hung receiver cannot pin a Celery worker slot."""

    @mock.patch('webhooks.tasks.get_hook_model')
    @mock.patch('webhooks.tasks.requests.post')
    def test_post_uses_connect_and_read_timeouts(self, post, get_hook_model):
        post.return_value = mock.Mock(status_code=200)
        deliver_hook('https://receiver.example.edu/hook', {'event': 'submission.created'}, hook_id=1)
        self.assertEqual(post.call_args.kwargs['timeout'], (5, 30))

    def test_task_has_hard_time_limits(self):
        self.assertEqual(deliver_hook.soft_time_limit, 60)
        self.assertEqual(deliver_hook.time_limit, 90)
