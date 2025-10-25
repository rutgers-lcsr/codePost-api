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


def safe_create_submissionfile_table(apps, schema_editor):
    """
    Safely create SubmissionFile table if it doesn't exist.
    Handles partial migration runs.
    """
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_submissionfile'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if table_exists:
            print("ℹ Table 'core_submissionfile' already exists, skipping creation")
            return
        
        # Create the table manually
        print("ℹ Creating table 'core_submissionfile'")
        cursor.execute("""
            CREATE TABLE `core_submissionfile` (
                `file_ptr_id` bigint NOT NULL PRIMARY KEY,
                CONSTRAINT `core_submissionfile_file_ptr_id_fk` 
                    FOREIGN KEY (`file_ptr_id`) 
                    REFERENCES `core_file` (`id`)
            )
        """)


def safe_create_assignmentfile_table(apps, schema_editor):
    """
    Safely create AssignmentFile table if it doesn't exist.
    """
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_assignmentfile'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if table_exists:
            print("ℹ Table 'core_assignmentfile' already exists, skipping creation")
            return
        
        print("ℹ Creating table 'core_assignmentfile'")
        cursor.execute("""
            CREATE TABLE `core_assignmentfile` (
                `file_ptr_id` bigint NOT NULL PRIMARY KEY,
                `assignment_id` bigint NOT NULL,
                `required` tinyint(1) NOT NULL DEFAULT 0,
                `description` longtext NOT NULL,
                CONSTRAINT `core_assignmentfile_file_ptr_id_fk` 
                    FOREIGN KEY (`file_ptr_id`) 
                    REFERENCES `core_file` (`id`),
                CONSTRAINT `core_assignmentfile_assignment_id_fk`
                    FOREIGN KEY (`assignment_id`)
                    REFERENCES `core_assignment` (`id`)
            )
        """)


def safe_create_coursefile_table(apps, schema_editor):
    """
    Safely create CourseFile table if it doesn't exist.
    """
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_coursefile'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if table_exists:
            print("ℹ Table 'core_coursefile' already exists, skipping creation")
            return
        
        print("ℹ Creating table 'core_coursefile'")
        cursor.execute("""
            CREATE TABLE `core_coursefile` (
                `file_ptr_id` bigint NOT NULL PRIMARY KEY,
                `course_id` bigint NOT NULL,
                CONSTRAINT `core_coursefile_file_ptr_id_fk` 
                    FOREIGN KEY (`file_ptr_id`) 
                    REFERENCES `core_file` (`id`),
                CONSTRAINT `core_coursefile_course_id_fk`
                    FOREIGN KEY (`course_id`)
                    REFERENCES `core_course` (`id`)
            )
        """)


def copy_submission_data_to_child_table(apps, schema_editor):
    """
    Copy submission_id and hiddenBeforePublish data from core_file table 
    to the new columns in core_submissionfile table.
    
    This runs after AddField creates the new columns in core_submissionfile,
    and before RemoveField deletes the old columns from core_file.
    """
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        # Check if the columns exist in both tables
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_submissionfile'
            AND COLUMN_NAME = 'submission_id'
        """)
        child_has_column = cursor.fetchone()[0] > 0
        
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'submission_id'
        """)
        parent_has_column = cursor.fetchone()[0] > 0
        
        if not child_has_column:
            print("ℹ Skipping data copy - submission_id not yet in core_submissionfile")
            return
        
        if not parent_has_column:
            print("ℹ Skipping data copy - submission_id already removed from core_file")
            return
        
        # Copy data from parent table columns to child table columns
        cursor.execute("""
            UPDATE core_submissionfile sf
            INNER JOIN core_file f ON sf.file_ptr_id = f.id
            SET 
                sf.submission_id = f.submission_id,
                sf.hiddenBeforePublish = f.hiddenBeforePublish
        """)
        
        rows_updated = cursor.rowcount
        print(f"✓ Copied submission data for {rows_updated} SubmissionFile records to child table")


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
        # Note: submission and hiddenBeforePublish are NOT defined here because they still exist in File parent class
        # They will be removed from File in Step 5, then added specifically to SubmissionFile in Step 5b/5c
        # Use SeparateDatabaseAndState to handle idempotent table creation
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
                    ],
                    options={
                        "abstract": False,
                    },
                    bases=("core.file",),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    safe_create_submissionfile_table,
                    migrations.RunPython.noop,
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
                        (
                            "required",
                            models.BooleanField(
                                default=False,
                                help_text="Whether this file is required for submission.",
                            ),
                        ),
                        (
                            "description",
                            models.TextField(
                                default="",
                                help_text="Description of the file template.",
                            ),
                        ),
                    ],
                    options={
                        "abstract": False,
                    },
                    bases=("core.file",),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    safe_create_assignmentfile_table,
                    migrations.RunPython.noop,
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
            ],
            database_operations=[
                migrations.RunPython(
                    safe_create_coursefile_table,
                    migrations.RunPython.noop,
                ),
            ],
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
        
        # Step 5: Add submission and hiddenBeforePublish to SubmissionFile child table FIRST
        # These will create NEW columns in core_submissionfile table
        migrations.AddField(
            model_name="submissionfile",
            name="submission",
            field=models.ForeignKey(
                help_text="The related submission_id.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="files",
                to="core.submission",
                null=True,  # Temporary, will be populated by data migration
            ),
        ),
        migrations.AddField(
            model_name="submissionfile",
            name="hiddenBeforePublish",
            field=models.BooleanField(
                default=False,
                help_text="Whether this file should hidden to students before their feedback has been published. This is for autogenerated test files that shouldn't be exposed to students on upload.",
            ),
        ),
        
        # Step 5b: Copy data from File columns to SubmissionFile columns
        migrations.RunPython(
            copy_submission_data_to_child_table,
            migrations.RunPython.noop,
        ),
        
        # Step 5c: Make submission field NOT NULL after data is copied
        migrations.AlterField(
            model_name="submissionfile",
            name="submission",
            field=models.ForeignKey(
                help_text="The related submission_id.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="files",
                to="core.submission",
            ),
        ),
        
        # Step 5d: NOW remove the fields from File parent table
        # This deletes the columns from core_file table
        migrations.RemoveField(
            model_name="file",
            name="submission",
        ),
        migrations.RemoveField(
            model_name="file",
            name="hiddenBeforePublish",
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
