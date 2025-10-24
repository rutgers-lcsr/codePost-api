# Generated migration for AssignmentDataSet model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_remove_filetemplate_code_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AssignmentDataSet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Identifier for the dataset (e.g., mnist, iris)', max_length=255)),
                ('description', models.TextField(blank=True, help_text='Human-readable description of the dataset contents')),
                ('mount_path', models.CharField(blank=True, help_text='Path where dataset is mounted (e.g., shared/mnist). Auto-generated from name if not specified.', max_length=512)),
                ('file', models.FileField(help_text='Dataset file (can be compressed or raw data)', max_length=512, upload_to='assignment_datasets/')),
                ('file_name', models.CharField(blank=True, help_text='Original filename', max_length=255)),
                ('file_size', models.BigIntegerField(blank=True, help_text='File size in bytes', null=True)),
                ('is_active', models.BooleanField(default=True, help_text='Whether this dataset should be mounted during execution')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('assignment', models.ForeignKey(help_text='Assignment this dataset belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='datasets', to='core.assignment')),
            ],
            options={
                'verbose_name': 'Assignment Dataset',
                'verbose_name_plural': 'Assignment Datasets',
                'ordering': ['assignment', 'name'],
                'unique_together': {('assignment', 'name')},
            },
        ),
    ]
