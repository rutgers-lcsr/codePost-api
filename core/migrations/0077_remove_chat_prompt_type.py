# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Data migration: remove the 'chat' prompt type and all associated data.
The agentic chat feature was removed in 0071_remove_agentic_chat.
"""
from django.db import migrations


def remove_chat_data(apps, schema_editor):
    SystemPromptVariant = apps.get_model('core', 'SystemPromptVariant')
    PromptExperiment = apps.get_model('core', 'PromptExperiment')
    PromptFeedback = apps.get_model('core', 'PromptFeedback')

    # Delete feedback linked to chat experiments
    chat_experiments = PromptExperiment.objects.filter(prompt_type='chat')
    PromptFeedback.objects.filter(experiment__in=chat_experiments).delete()

    # Delete chat experiments
    chat_experiments.delete()

    # Delete chat variants
    SystemPromptVariant.objects.filter(prompt_type='chat').delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0076_behavioral_feedback_fields'),
    ]

    operations = [
        migrations.RunPython(remove_chat_data, noop),
    ]
