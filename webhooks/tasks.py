import requests
import json

"""
FIXME
Task is deprecated
https://github.com/celery/celery/issues/6406
"""
# from celery.task import Task
from celery.exceptions import MaxRetriesExceededError

from django.core.serializers.json import DjangoJSONEncoder

from webhooks.utils import get_hook_model


def slack_webhook_error(topic, target, hook_id, payload):
    from util.slack import Slack

    slack_client = Slack()

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*{}*".format(topic)}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*Target:*\n{}".format(str(target))},
                {"type": "mrkdwn", "text": "*Hook ID:*\n{}".format(str(hook_id))},
                {
                    "type": "mrkdwn",
                    "text": "*Data:*\n{}".format(
                        json.dumps(payload, cls=DjangoJSONEncoder)
                    ),
                },
            ],
        },
    ]

    slack_client.send_message(
        topic, blocks=blocks, channel="user_notifications_webhooks"
    )


# class DeliverHook(Task):
class DeliverHook:
    max_retries = 3

    def run(self, target, payload, instance=None, hook_id=None, **kwargs):
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
        except requests.ConnectionError:
            delay_in_seconds = 2**self.request.retries
            try:
                self.retry(countdown=delay_in_seconds)
            except MaxRetriesExceededError:
                hook.last_triggered_status = "Could not connect"
                hook.save()
                # We could optionally just deactivate hooks if they fail
                slack_webhook_error(
                    "Webhook Failed to Connect", target, hook_id, payload
                )
        except:
            hook.last_triggered_status = "Unknown error"
            hook.save()
            slack_webhook_error("Unknown Webhook Error", target, hook_id, payload)


def deliver_hook_wrapper(target, payload, instance=None, hook=None, **kwargs):
    if hook:
        kwargs["hook_id"] = hook.id
    return None
    return DeliverHook.delay(target, payload, **kwargs)
