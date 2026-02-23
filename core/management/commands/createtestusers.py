# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from core.models import Course, Organization, Assignment, AssignmentFile, Submission, SubmissionFile

class Command(BaseCommand):
    help = 'Creates test users and enrolls them in ALL existing courses for development'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('This command can only be run in DEBUG mode.')

        # Target Organization (from Admin)
        # Find the first superuser to determine the "Dev" context
        admin_user = User.objects.filter(is_superuser=True).order_by('id').first()
        target_org = None
        
        if admin_user:
            # Ensure profile exists (signal should execute, but safe to check)
            if hasattr(admin_user, 'profile') and admin_user.profile.organization:
                target_org = admin_user.profile.organization
                self.stdout.write(self.style.SUCCESS(f"Targeting Admin Organization: {target_org.name} ({target_org.shortname})"))
            else:
                 self.stdout.write(self.style.WARNING(f"Admin user {admin_user.username} has no organization. Test users will have valid profiles but no specific org."))
        else:
            self.stdout.write(self.style.WARNING("No superuser found. Cannot determine target organization. Run 'createsuperuser' first if needed."))


        # 1. Pure Student
        student, created = User.objects.get_or_create(
            username='student_only',
            defaults={
                'email': 'student_only@dev.edu',
                'first_name': 'Test',
                'last_name': 'Student'
            }
        )
        if created:
            student.set_password('password')
            student.save()
            self.stdout.write(self.style.SUCCESS('Created user: student_only'))
        
        if target_org:
            student.profile.organization = target_org
            student.profile.save()

        # 2. Pure Grader (Basic)
        grader_basic, created = User.objects.get_or_create(
            username='grader_basic',
            defaults={
                'email': 'grader_basic@dev.edu',
                'first_name': 'Test',
                'last_name': 'GraderBasic'
            }
        )
        if created:
            grader_basic.set_password('password')
            grader_basic.save()
            self.stdout.write(self.style.SUCCESS('Created user: grader_basic'))
        
        if target_org:
            grader_basic.profile.organization = target_org
            grader_basic.profile.save()

        # 3. Grader (Rubric)
        grader_rubric, created = User.objects.get_or_create(
            username='grader_rubric',
            defaults={
                'email': 'grader_rubric@dev.edu',
                'first_name': 'Test',
                'last_name': 'GraderRubric'
            }
        )
        if created:
            grader_rubric.set_password('password')
            grader_rubric.save()
            self.stdout.write(self.style.SUCCESS('Created user: grader_rubric'))
        
        if target_org:
            grader_rubric.profile.organization = target_org
            grader_rubric.profile.save()

        # 4. Super Grader
        grader_super, created = User.objects.get_or_create(
            username='grader_super',
            defaults={
                'email': 'grader_super@dev.edu',
                'first_name': 'Test',
                'last_name': 'GraderSuper'
            }
        )
        if created:
            grader_super.set_password('password')
            grader_super.save()
            self.stdout.write(self.style.SUCCESS('Created user: grader_super'))
        
        if target_org:
            grader_super.profile.organization = target_org
            grader_super.profile.save()

        # 5. Pure Course Admin
        cadmin, created = User.objects.get_or_create(
            username='course_admin_only',
            defaults={
                'email': 'course_admin_only@dev.edu',
                'first_name': 'Test',
                'last_name': 'Admin'
            }
        )
        if created:
            cadmin.set_password('password')
            cadmin.save()
            self.stdout.write(self.style.SUCCESS('Created user: course_admin_only'))
        
        if target_org:
            cadmin.profile.organization = target_org
            cadmin.profile.save()
        
        # Enroll in courses
        if target_org:
            courses = Course.objects.filter(organization=target_org)
        else:
            courses = Course.objects.all()

        for course in courses:
            self.stdout.write(f"Enrolling test users in {course.name}...")
            course.students.add(student)
            
            # Add all graders to graders list first
            course.graders.add(grader_basic)
            course.graders.add(grader_rubric)
            course.graders.add(grader_super)
            
            # Specific permissions
            course.rubricEditors.add(grader_rubric)
            
            course.superGraders.add(grader_super)
            
            course.courseAdmins.add(cadmin)

        self.stdout.write(self.style.SUCCESS(f'Successfully enrolled test users in {courses.count()} courses.'))
