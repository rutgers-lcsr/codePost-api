# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Escape hatch for the lifecycle migration: bulk-set Assignment.state for a course.

If an instructor is surprised by the 0140 mapping (e.g. an assignment they treated as
an announcement landed in 'published'), this moves a course's assignments — or a single
assignment — to the intended state in one command. Uses save() (not queryset.update) so
the legacy-boolean sync, publishedAt stamp, and signals all run.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import Assignment, Course, ASSIGNMENT_STATE_CHOICES

VALID_STATES = [value for value, _label in ASSIGNMENT_STATE_CHOICES]


class Command(BaseCommand):
    help = (
        "Bulk-set the lifecycle state for a course's assignments (or one assignment). "
        "Example: set_assignment_state --course-id 42 --state visible --dry-run"
    )

    def add_arguments(self, parser):
        parser.add_argument("--course-id", type=int, required=True,
                            help="Course.id whose assignments to update.")
        parser.add_argument("--assignment-id", type=int, default=None,
                            help="Restrict to a single Assignment.id within the course.")
        parser.add_argument("--state", type=str, required=True, choices=VALID_STATES,
                            help="Target lifecycle state.")
        parser.add_argument("--from-state", type=str, default=None, choices=VALID_STATES,
                            help="Only update assignments currently in this state.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Print what would change without saving.")

    def handle(self, *args, **options):
        course_id = options["course_id"]
        target = options["state"]

        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            raise CommandError(f"Course {course_id} does not exist.")

        assignments = Assignment.objects.filter(course=course)
        if options["assignment_id"] is not None:
            assignments = assignments.filter(pk=options["assignment_id"])
            if not assignments.exists():
                raise CommandError(
                    f"Assignment {options['assignment_id']} does not exist in course {course_id}.")
        if options["from_state"] is not None:
            assignments = assignments.filter(state=options["from_state"])

        changed = 0
        for assignment in assignments:
            if assignment.state == target:
                continue
            self.stdout.write(
                f"{'[dry-run] ' if options['dry_run'] else ''}"
                f"assignment {assignment.id} ({assignment.name}): {assignment.state} -> {target}"
            )
            if not options["dry_run"]:
                assignment.state = target
                assignment.save()
            changed += 1

        self.stdout.write(
            f"{'Would update' if options['dry_run'] else 'Updated'} {changed} assignment(s) "
            f"in course {course_id} ({course.name} {course.period})."
        )
