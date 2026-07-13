# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0070_add_comment_feedback_event_type"),
    ]

    operations = [
        # Drop ChatMessage first (FK to ChatConversation)
        migrations.DeleteModel(name="ChatMessage"),
        migrations.DeleteModel(name="ChatConversation"),

        # Remove ai_chat_disabled from Organization and Course
        migrations.RemoveField(model_name="organization", name="ai_chat_disabled"),
        migrations.RemoveField(model_name="course", name="ai_chat_disabled"),
    ]
