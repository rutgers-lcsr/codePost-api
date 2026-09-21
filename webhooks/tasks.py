# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import requests
import json
import logging
from core.logging import logEvent

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from django.core.serializers.json import DjangoJSONEncoder

from webhooks.utils import get_hook_model



@shared_task(bind=True, max_retries=3, soft_time_limit=60, time_limit=90)
def deliver_hook(self, target, payload, instance=None, hook_id=None, **kwargs):
    """
    target:     the url to receive the payload.
    payload:    a python primitive data structure
    instance:   a possibly null "trigger" instance
    hook:       the defining Hook object (useful for removing)
    """
    HookModel = get_hook_model()
    hook = HookModel.objects.get(id=hook_id)

    try:
        response = requests.post(
            url=target,
            data=json.dumps(payload, cls=DjangoJSONEncoder),
            headers={"Content-Type": "application/json"},
            # (connect, read): a hung receiver must not pin a worker slot indefinitely.
            timeout=(5, 30),
        )
        if response.status_code >= 500:
            hook.last_triggered_status = response.status_code
            hook.save()
            response.raise_for_status()
        elif response.status_code == 410 and hook_id:
            hook.last_triggered_status = response.status_code
            hook.is_active = False
            hook.save()
        else:
            hook.last_triggered_status = response.status_code
            hook.save()
    except (requests.ConnectionError, requests.Timeout):
        delay_in_seconds = 2**self.request.retries
        try:
            self.retry(countdown=delay_in_seconds)
        except MaxRetriesExceededError:
            hook.last_triggered_status = "Could not connect"
            hook.save()
            # We could optionally just deactivate hooks if they fail
           
            logEvent(
                "Webhook Connection Error",
                message=f"Failed to connect to {target} with hook ID {hook_id}",
                level=logging.ERROR,
            )
    except:
        hook.last_triggered_status = "Unknown error"
        hook.save()
        logEvent(
            "Webhook Error",
            message=f"Unknown error delivering webhook to {target} with hook ID {hook_id}",
            level=logging.ERROR,
        )


def deliver_hook_wrapper(target, payload, instance=None, hook=None, **kwargs):
    if hook:
        kwargs["hook_id"] = hook.id


    print(f"Delivering hook to {target} with payload: {payload}")
    return deliver_hook.delay(target, payload, **kwargs)  # type: ignore[reportCallIssue]


