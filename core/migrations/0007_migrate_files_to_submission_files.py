# Generated manually to handle File -> SubmissionFile/AssignmentFile/CourseFile migration
# This migration handles both clean (production) and partial (staging) states

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def safe_rename_code_to_data(apps, schema_editor):
    """Check if code column exists before renaming"""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'code'
        """)
        if cursor.fetchone()[0] > 0:
            print("→ Renaming 'code' to 'data'")
            cursor.execute("ALTER TABLE core_file CHANGE COLUMN code data LONGTEXT NOT NULL")
        else:
            print("✓ Column 'code' already renamed to 'data', skipping")


def rename_fields_in_file(apps, schema_editor):
    """
    Rename submission and hiddenBeforePublish to temporary names.
    This allows us to add them to SubmissionFile without conflicts.
    Also drops the foreign key constraint on submission_id.
    """
    with schema_editor.connection.cursor() as cursor:
        # Check if submission_id exists (not already renamed)
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'submission_id'
        """)
        
        if cursor.fetchone()[0] > 0:
            # First, drop the foreign key constraint
            cursor.execute("""
                SELECT CONSTRAINT_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'core_file'
                AND COLUMN_NAME = 'submission_id'
                AND REFERENCED_TABLE_NAME IS NOT NULL
            """)
            fk_result = cursor.fetchone()
            if fk_result:
                fk_name = fk_result[0]
                print(f"→ Dropping foreign key constraint {fk_name}")
                cursor.execute(f"ALTER TABLE core_file DROP FOREIGN KEY {fk_name}")
            
            print("→ Renaming submission_id to temp_submission_id in File")
            cursor.execute("ALTER TABLE core_file CHANGE COLUMN submission_id temp_submission_id bigint")
        else:
            print("✓ submission_id already renamed or removed")
        
        # Check if hiddenBeforePublish exists (not already renamed)
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'hiddenBeforePublish'
        """)
        
        if cursor.fetchone()[0] > 0:
            print("→ Renaming hiddenBeforePublish to temp_hiddenBeforePublish in File")
            cursor.execute("ALTER TABLE core_file CHANGE COLUMN hiddenBeforePublish temp_hiddenBeforePublish tinyint(1) NOT NULL DEFAULT 0")
        else:
            print("✓ hiddenBeforePublish already renamed or removed")


def check_hidden_in_file(apps, schema_editor):
    """Check if hiddenBeforePublish exists in File table"""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'hiddenBeforePublish'
        """)
        return cursor.fetchone()[0] > 0


def migrate_existing_files_to_submissionfiles(apps, schema_editor):
    """
    Migrate existing File records (that have submission_id) to SubmissionFile records.
    This happens AFTER SubmissionFile table is created but BEFORE fields are removed from File.
    """
    with schema_editor.connection.cursor() as cursor:
        # Check if temp_submission_id exists in File (after rename)
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'temp_submission_id'
        """)
        
        if cursor.fetchone()[0] == 0:
            print("✓ temp_submission_id doesn't exist, skipping data migration")
            return
        
        # Check if SubmissionFile records already exist
        cursor.execute("SELECT COUNT(*) FROM core_submissionfile")
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            print(f"✓ SubmissionFile records already exist ({existing_count}), skipping data migration")
            return
        
        # Migrate: Create SubmissionFile record for each File that has a submission
        # This creates the child table entry pointing to the existing File parent record
        cursor.execute("""
            INSERT INTO core_submissionfile (file_ptr_id)
            SELECT id FROM core_file WHERE temp_submission_id IS NOT NULL
        """)
        
        rows_migrated = cursor.rowcount
        print(f"✓ Migrated {rows_migrated} File records to SubmissionFile")


def migrate_filetemplates_to_assignmentfiles(apps, schema_editor):
    """
    Migrate FileTemplate records to AssignmentFile records.
    Creates new File records and corresponding AssignmentFile child records.
    """
    with schema_editor.connection.cursor() as cursor:
        # Check if FileTemplate table exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_filetemplate'
        """)
        
        if cursor.fetchone()[0] == 0:
            print("✓ FileTemplate table doesn't exist, skipping AssignmentFile migration")
            return
        
        # Check if AssignmentFile records already exist
        cursor.execute("SELECT COUNT(*) FROM core_assignmentfile")
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            print(f"✓ AssignmentFile records already exist ({existing_count}), skipping migration")
            return
        
        # Get FileTemplate records
        cursor.execute("""
            SELECT id, name, code, extension, path, assignment_id, required, description, created, modified
            FROM core_filetemplate
        """)
        
        templates = cursor.fetchall()
        if not templates:
            print("✓ No FileTemplate records to migrate")
            return
        
        files_created = 0
        for template_id, name, code, extension, path, assignment_id, required, description, created, modified in templates:
            # Create File base record
            cursor.execute("""
                INSERT INTO core_file (name, data, extension, path, created, modified)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, [name, code or '', extension, path, created, modified])
            
            file_id = cursor.lastrowid
            
            # Create AssignmentFile child record
            cursor.execute("""
                INSERT INTO core_assignmentfile (file_ptr_id, assignment_id, required, description)
                VALUES (%s, %s, %s, %s)
            """, [file_id, assignment_id, required or False, description or ''])
            
            files_created += 1
        
        print(f"✓ Migrated {files_created} FileTemplate records to AssignmentFile")


def copy_submission_data_from_file(apps, schema_editor):
    """
    Copy temp_submission_id and temp_hiddenBeforePublish from File table to SubmissionFile table.
    This runs after the columns are added to SubmissionFile.
    """
    with schema_editor.connection.cursor() as cursor:
        # Copy data from File temp columns to SubmissionFile
        cursor.execute("""
            UPDATE core_submissionfile sf
            INNER JOIN core_file f ON sf.file_ptr_id = f.id
            SET 
                sf.submission_id = f.temp_submission_id,
                sf.hiddenBeforePublish = COALESCE(f.temp_hiddenBeforePublish, 0)
        """)
        
        rows_updated = cursor.rowcount
        print(f"✓ Copied submission data for {rows_updated} SubmissionFile records")


def cleanup_temp_columns(apps, schema_editor):
    """
    Drop temporary columns from File table.
    Drops any remaining indexes first to avoid constraint errors.
    """
    with schema_editor.connection.cursor() as cursor:
        # Check if temp_submission_id exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'temp_submission_id'
        """)
        
        if cursor.fetchone()[0] > 0:
            # Drop any indexes on temp_submission_id
            cursor.execute("""
                SELECT DISTINCT INDEX_NAME
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'core_file'
                AND COLUMN_NAME = 'temp_submission_id'
                AND INDEX_NAME != 'PRIMARY'
            """)
            
            for (index_name,) in cursor.fetchall():
                try:
                    print(f"→ Dropping index {index_name} on temp_submission_id")
                    cursor.execute(f"ALTER TABLE core_file DROP INDEX {index_name}")
                except Exception as e:
                    print(f"  Note: Could not drop index {index_name}: {e}")
            
            print("→ Dropping temp_submission_id column")
            cursor.execute("ALTER TABLE core_file DROP COLUMN temp_submission_id")
        
        # Check if temp_hiddenBeforePublish exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'temp_hiddenBeforePublish'
        """)
        
        if cursor.fetchone()[0] > 0:
            print("→ Dropping temp_hiddenBeforePublish column")
            cursor.execute("ALTER TABLE core_file DROP COLUMN temp_hiddenBeforePublish")
        
        print("✓ Cleaned up temporary columns")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_profile_ispasswordset_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1: Safely rename 'code' to 'data' (handles partial state)
        migrations.RunPython(
            safe_rename_code_to_data,
            migrations.RunPython.noop,
        ),
        
        # Step 1b: Rename submission and hiddenBeforePublish to temporary names in database
        # This allows us to add them to SubmissionFile without field name conflicts
        migrations.RunPython(
            rename_fields_in_file,
            migrations.RunPython.noop,
        ),
        
        # Step 1c: Remove from Django's state ONLY (database columns already renamed above)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="file",
                    name="submission",
                ),
                migrations.RemoveField(
                    model_name="file",
                    name="hiddenBeforePublish",
                ),
            ],
            database_operations=[],  # No database changes - already renamed in Step 1b
        ),
        
        # Step 2: Alter File model fields
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
        
        # Step 3: Create SubmissionFile - fields depend on what's still in File
        # If hiddenBeforePublish is still in File, don't define it here (will inherit)
        # If it's been removed from File, define it here
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
                # submission and hiddenBeforePublish will be added after removal from File
            ],
            options={
                "abstract": False,
            },
            bases=("core.file",),
        ),
        
        # Step 4: Create AssignmentFile child model
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
        
        # Step 5: Create CourseFile child model
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
        
        # Step 5b: Migrate existing File data to SubmissionFile
        # This happens AFTER creating the child tables but BEFORE removing fields from File
        migrations.RunPython(
            migrate_existing_files_to_submissionfiles,
            migrations.RunPython.noop,
        ),
        
        # Step 5c: Migrate FileTemplate data to AssignmentFile
        migrations.RunPython(
            migrate_filetemplates_to_assignmentfiles,
            migrations.RunPython.noop,
        ),
        
        # Step 6a: Add submission and hiddenBeforePublish to SubmissionFile BEFORE removing from File
        # Add as nullable first, then populate, then make NOT NULL
        migrations.AddField(
            model_name="submissionfile",
            name="submission",
            field=models.ForeignKey(
                help_text="The related submission_id.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="files",
                to="core.submission",
                null=True,  # Temporarily nullable
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
        
        # Step 6b: Populate submission_id and hiddenBeforePublish from parent File table
        migrations.RunPython(
            copy_submission_data_from_file,
            migrations.RunPython.noop,
        ),
        
        # Step 6c: Make submission NOT NULL now that data is populated
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
        
        # Step 6d: NOW remove temp fields from File model (after copying to SubmissionFile)
        # Use custom function to safely drop columns and their indexes
        migrations.RunPython(
            cleanup_temp_columns,
            migrations.RunPython.noop,
        ),
        
        # Step 7: Update other model fields (from original migration)
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
