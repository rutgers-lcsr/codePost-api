# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.core.management.base import BaseCommand

from core.models import SystemPromptVariant
from core.prompts.registry import prompt_registry


class Command(BaseCommand):
    help = 'Ensure every registered prompt type has an active SystemPromptVariant seeded from the registry default.'

    def handle(self, *args, **options):
        created_count = 0
        for entry in prompt_registry.all():
            if not SystemPromptVariant.objects.filter(prompt_type=entry.key, status='active').exists():
                SystemPromptVariant.objects.create(
                    prompt_type=entry.key,
                    name=f'{entry.label} (default)',
                    text=entry.get_default_template(),
                    status='active',
                    version=1,
                )
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  Created active variant for "{entry.key}"'))

        if created_count == 0:
            self.stdout.write(self.style.SUCCESS('All prompt types already have active variants.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Seeded {created_count} prompt variant(s).'))
