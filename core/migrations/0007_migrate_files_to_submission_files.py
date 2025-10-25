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
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        # Check if SubmissionFile table is actually usable
        try:
            cursor.execute("SELECT COUNT(*) FROM core_submissionfile")
            existing_count = cursor.fetchone()[0]
            
            if existing_count > 0:
                print(f"ℹ SubmissionFile records already exist ({existing_count} records), skipping migration")
                return
        except Exception as e:
            if "doesn't exist" in str(e) or "1932" in str(e):
                print(f"ℹ Warning: core_submissionfile table not accessible: {e}")
                print("ℹ Skipping SubmissionFile data migration - table will be created first")
                return
            else:
                raise
        
        # Check if submission_id column exists in core_file (not yet removed)
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_file'
            AND COLUMN_NAME = 'submission_id'
        """)
        submission_in_file = cursor.fetchone()[0] > 0
        
        if not submission_in_file:
            print("ℹ submission_id already removed from File, skipping SubmissionFile migration")
            return
        
        # Migrate File records with submissions to SubmissionFile
        # Use raw SQL to avoid ORM state issues
        cursor.execute("""
            INSERT INTO core_submissionfile (file_ptr_id)
            SELECT id FROM core_file WHERE submission_id IS NOT NULL
        """)
        
        rows_created = cursor.rowcount
        if rows_created > 0:
            print(f"✓ Migrated {rows_created} File records to SubmissionFile")
        else:
            print("ℹ No File records with submissions to migrate")


def migrate_filetemplates_to_assignment_files(apps, schema_editor):
    """
    Migrate existing FileTemplate records to AssignmentFile records.
    This creates new File base records and then AssignmentFile child records.
    """
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        # Check if AssignmentFile table is actually usable
        try:
            cursor.execute("SELECT COUNT(*) FROM core_assignmentfile")
            existing_count = cursor.fetchone()[0]
            
            if existing_count > 0:
                print(f"ℹ AssignmentFile records already exist ({existing_count} records), skipping migration")
                return
        except Exception as e:
            if "doesn't exist" in str(e) or "1932" in str(e):
                print(f"ℹ Warning: core_assignmentfile table not accessible: {e}")
                print("ℹ Skipping AssignmentFile data migration - table will be created first")
                return
            else:
                raise
        
        # Check if FileTemplate table exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'core_filetemplate'
        """)
        template_exists = cursor.fetchone()[0] > 0
        
        if not template_exists:
            print("ℹ FileTemplate table doesn't exist, skipping AssignmentFile migration")
            return
        
        # Count FileTemplate records
        cursor.execute("SELECT COUNT(*) FROM core_filetemplate")
        template_count = cursor.fetchone()[0]
        
        if template_count == 0:
            print("ℹ No FileTemplate records to migrate")
            return
        
        # Get FileTemplate records and create File + AssignmentFile records
        # Use raw SQL to avoid ORM state issues with code/data field
        cursor.execute("""
            SELECT id, name, code, extension, path, assignment_id, required, description, created, modified
            FROM core_filetemplate
        """)
        
        templates = cursor.fetchall()
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
            """, [file_id, assignment_id, required, description or ''])
            
            files_created += 1
        
        print(f"✓ Migrated {files_created} FileTemplate records to AssignmentFile")


def safe_create_submissionfile_table(apps, schema_editor):
    """
    Safely create SubmissionFile table if it doesn't exist.
    Handles partial migration runs and corrupted table states.
    """
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        # Try to check if table is actually usable (not just in information_schema)
        try:
            cursor.execute("SELECT 1 FROM core_submissionfile LIMIT 0")
            print("ℹ Table 'core_submissionfile' already exists and is usable, skipping creation")
            return
        except Exception as e:
            # Table doesn't exist or is corrupted, try to drop and recreate
            if "doesn't exist" in str(e) or "1932" in str(e):
                print(f"ℹ Table 'core_submissionfile' is corrupted or doesn't exist: {e}")
                try:
                    cursor.execute("DROP TABLE IF EXISTS core_submissionfile")
                    print("ℹ Dropped corrupted table 'core_submissionfile'")
                except:
                    pass
            else:
                raise
        
        # Create the table
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
    Handles partial migration runs and corrupted table states.
    """
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        try:
            cursor.execute("SELECT 1 FROM core_assignmentfile LIMIT 0")
            print("ℹ Table 'core_assignmentfile' already exists and is usable, skipping creation")
            return
        except Exception as e:
            if "doesn't exist" in str(e) or "1932" in str(e):
                print(f"ℹ Table 'core_assignmentfile' is corrupted or doesn't exist: {e}")
                try:
                    cursor.execute("DROP TABLE IF EXISTS core_assignmentfile")
                    print("ℹ Dropped corrupted table 'core_assignmentfile'")
                except:
                    pass
            else:
                raise
        
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
    Handles partial migration runs and corrupted table states.
    """
    db_alias = schema_editor.connection.alias
    
    with schema_editor.connection.cursor() as cursor:
        try:
            cursor.execute("SELECT 1 FROM core_coursefile LIMIT 0")
            print("ℹ Table 'core_coursefile' already exists and is usable, skipping creation")
            return
        except Exception as e:
            if "doesn't exist" in str(e) or "1932" in str(e):
                print(f"ℹ Table 'core_coursefile' is corrupted or doesn't exist: {e}")
                try:
                    cursor.execute("DROP TABLE IF EXISTS core_coursefile")
                    print("ℹ Dropped corrupted table 'core_coursefile'")
                except:
                    pass
            else:
                raise
        
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
