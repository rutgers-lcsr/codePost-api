# Generated manually to handle File -> SubmissionFile migration

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def safe_rename_code_to_data(apps, schema_editor):
    """
    Safely rename 'code' to 'data' if the 'code' column exists.
    This handles partial migration runs where the rename may have already occurred.
    """
    db_alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        # Check if 'code' column exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'code'
        """)
        code_exists = cursor.fetchone()[0] > 0
        
        if code_exists:
            print("ℹ Renaming 'code' column to 'data' in core_file table")
            cursor.execute("ALTER TABLE core_file CHANGE COLUMN code data LONGTEXT NOT NULL")
        else:
            print("ℹ Column 'code' already renamed to 'data' (or never existed), skipping rename")


def reverse_rename_data_to_code(apps, schema_editor):
    """
    Reverse the rename operation
    """
    db_alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE core_file CHANGE COLUMN data code LONGTEXT NOT NULL")


def migrate_files_to_submission_files(apps, schema_editor):
    """
    Migrate existing File records with submissions to SubmissionFile records.
    This preserves the File IDs so that Comment and other foreign key references remain valid.
    """
    File = apps.get_model("core", "File")
    SubmissionFile = apps.get_model("core", "SubmissionFile")
    
    db_alias = schema_editor.connection.alias
    
    # Get all File records that have submissions (must do this BEFORE removing the field)
    files_with_submissions = File.objects.using(db_alias).filter(submission__isnull=False)
    
    submission_files_to_create = []
    for file_obj in files_with_submissions:
        # Create SubmissionFile using the SAME ID as the original File
        # This preserves foreign key relationships (like Comment.file_id)
        submission_file = SubmissionFile(
            file_ptr_id=file_obj.id,
            submission_id=file_obj.submission_id,
            hiddenBeforePublish=getattr(file_obj, 'hiddenBeforePublish', False),
        )
        submission_files_to_create.append(submission_file)
    
    if submission_files_to_create:
        SubmissionFile.objects.using(db_alias).bulk_create(submission_files_to_create)
        print(f"✓ Migrated {len(submission_files_to_create)} File records to SubmissionFile")
    else:
        print("ℹ No File records with submissions to migrate")


def migrate_filetemplates_to_assignment_files(apps, schema_editor):
    """
    Migrate existing FileTemplate records to AssignmentFile records.
    This creates new File base records and then AssignmentFile child records.
    """
    FileTemplate = apps.get_model("core", "FileTemplate")
    File = apps.get_model("core", "File")
    AssignmentFile = apps.get_model("core", "AssignmentFile")
    
    db_alias = schema_editor.connection.alias
    
    # Get all FileTemplate records
    file_templates = FileTemplate.objects.using(db_alias).all()
    
    if not file_templates.exists():
        print("ℹ No FileTemplate records to migrate")
        return
    
    files_to_create = []
    assignment_files_to_create = []
    
    for template in file_templates:
        # First create the File base record
        file_obj = File(
            name=template.name,
            data=getattr(template, 'code', ''),  # Rename code → data
            extension=template.extension,
            path=template.path,
            created=template.created,
            modified=template.modified,
        )
        files_to_create.append(file_obj)
    
    # Bulk create File records
    created_files = File.objects.using(db_alias).bulk_create(files_to_create)
    print(f"✓ Created {len(created_files)} File base records from FileTemplate")
    
    # Now create AssignmentFile child records for each File
    # We need to get the IDs that were just created
    file_templates = list(FileTemplate.objects.using(db_alias).all())
    created_files_list = list(File.objects.using(db_alias).order_by('-id')[:len(file_templates)])
    created_files_list.reverse()  # Match the order
    
    for i, template in enumerate(file_templates):
        file_id = created_files_list[i].id
        assignment_file = AssignmentFile(
            file_ptr_id=file_id,
            assignment_id=template.assignment_id,
            required=template.required,
            description=getattr(template, 'description', ''),
        )
        assignment_files_to_create.append(assignment_file)
    
    AssignmentFile.objects.using(db_alias).bulk_create(assignment_files_to_create)
    print(f"✓ Migrated {len(assignment_files_to_create)} FileTemplate records to AssignmentFile")


def reverse_migrate_assignment_files(apps, schema_editor):
    """
    Reverse migration - remove all AssignmentFile records created from FileTemplate
    (The File base records will be deleted by cascade, but FileTemplate records remain)
    """
    AssignmentFile = apps.get_model("core", "AssignmentFile")
    db_alias = schema_editor.connection.alias
    
    # We can't perfectly reverse this, but we can delete AssignmentFile records
    # that were created from FileTemplate (they won't have comments pointing to them)
    count = AssignmentFile.objects.using(db_alias).count()
    AssignmentFile.objects.using(db_alias).all().delete()
    print(f"✓ Removed {count} AssignmentFile records")


def reverse_migrate_submission_files(apps, schema_editor):
    """
    Reverse migration - remove all SubmissionFile records
    (The File records will remain with their data intact)
    """
    SubmissionFile = apps.get_model("core", "SubmissionFile")
    db_alias = schema_editor.connection.alias
    
    count = SubmissionFile.objects.using(db_alias).count()
    SubmissionFile.objects.using(db_alias).all().delete()
    print(f"✓ Removed {count} SubmissionFile records")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_profile_ispasswordset_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1: Safely rename 'code' field to 'data' on File model (handles partial migrations)
        migrations.RunPython(
            safe_rename_code_to_data,
            reverse_rename_data_to_code,
        ),
        
        # Step 2: Alter other fields on File model
        migrations.AlterField(
            model_name="file",
            name="name",
            field=models.CharField(help_text="The name of the file.", max_length=250),
        ),
        migrations.AlterField(
            model_name="file",
            name="path",
            field=models.CharField(
                blank=True,
                help_text="Optional file path, delimited by slashes, to indicate a directory structure.",
                max_length=500,
                null=True,
            ),
        ),
        
        # Step 3: Create new child models (BEFORE removing fields from File)
        # Note: hiddenBeforePublish is NOT defined here because it still exists in File parent class
        # It will be removed from File in Step 5, making it specific to SubmissionFile
        migrations.CreateModel(
            name="SubmissionFile",
            fields=[
                (
                    "file_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.file",
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        help_text="The related submission_id.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="files",
                        to="core.submission",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("core.file",),
        ),
        migrations.CreateModel(
            name="AssignmentFile",
            fields=[
                (
                    "file_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.file",
                    ),
                ),
                (
                    "assignment",
                    models.ForeignKey(
                        help_text="The related assignment_id.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="files",
                        to="core.assignment",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("core.file",),
        ),
        migrations.CreateModel(
            name="CourseFile",
            fields=[
                (
                    "file_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.file",
                    ),
                ),
                (
                    "course",
                    models.ForeignKey(
                        help_text="The related course_id.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="files",
                        to="core.course",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("core.file",),
        ),
        
        # Step 4a: CRITICAL - Migrate existing File→SubmissionFile data BEFORE removing fields
        # This creates SubmissionFile records using the same IDs as existing Files
        # so that foreign key references (like Comment.file_id) remain valid
        migrations.RunPython(
            migrate_files_to_submission_files,
            reverse_migrate_submission_files,
        ),
        
        # Step 4b: CRITICAL - Migrate FileTemplate→AssignmentFile data
        # This creates new File base records and AssignmentFile child records
        # Must happen BEFORE FileTemplate fields are removed in migration 0008-0009
        migrations.RunPython(
            migrate_filetemplates_to_assignment_files,
            reverse_migrate_assignment_files,
        ),
        
        # Step 5: NOW we can safely remove fields from File
        # The data has been preserved in SubmissionFile records
        migrations.RemoveField(
            model_name="file",
            name="submission",
        ),
        migrations.RemoveField(
            model_name="file",
            name="hiddenBeforePublish",
        ),
        
        # Step 5b: Add hiddenBeforePublish to SubmissionFile now that it's removed from File
        # This makes the field specific to SubmissionFile only
        migrations.AddField(
            model_name="submissionfile",
            name="hiddenBeforePublish",
            field=models.BooleanField(
                default=False,
                help_text="Whether this file should hidden to students before their feedback has been published. This is for autogenerated test files that shouldn't be exposed to students on upload.",
            ),
        ),
        
        # Step 6: Update other model fields
        migrations.AlterField(
            model_name="assignment",
            name="uploadDueDate",
            field=models.DateTimeField(
                help_text="The date after which students are not allowed to upload submissions. Only useful if allowStudentUpload is set to True.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="course",
            name="inactive_courseAdmins",
            field=models.ManyToManyField(
                blank=True,
                help_text="A list of usernames of admins inactive in the course.",
                related_name="courseAdmin_inactive_courses",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="course",
            name="inactive_graders",
            field=models.ManyToManyField(
                blank=True,
                help_text="A list of usernames of graders inactive in the course.",
                related_name="grader_inactive_courses",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="course",
            name="inactive_students",
            field=models.ManyToManyField(
                blank=True,
                help_text="A list of usernames of students unenrolled in the course.",
                related_name="student_inactive_courses",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
