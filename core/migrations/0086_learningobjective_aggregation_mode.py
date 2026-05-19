# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0085_add_hidden_tests_and_learning_objectives'),
    ]

    operations = [
        migrations.AddField(
            model_name='learningobjective',
            name='aggregationMode',
            field=models.CharField(
                choices=[
                    ('all', 'All linked tests must pass'),
                    ('any', 'At least one linked test must pass'),
                    ('percentage', 'Percentage of linked tests that pass'),
                    ('points_weighted', 'Weighted by test point values'),
                ],
                default='all',
                help_text='How to aggregate results from multiple linked tests.',
                max_length=16,
            ),
        ),
    ]
