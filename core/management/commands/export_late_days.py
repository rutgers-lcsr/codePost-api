# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import csv
import math
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Submission, Course


SECONDS_PER_DAY = 60 * 60 * 24


class Command(BaseCommand):
    help = (
        "Export total late days per student for a single course into CSV.\n"
        "Output columns: user_email,days_late\n"
        "Late days are computed from (Submission.dateUploaded - Assignment.uploadDueDate).\n"
        "All students in the course are included, starting at 0 days."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--course-id",
            type=int,
            required=True,
            help="Course.id to export late days for.",
        )
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            default="-",
            help="Output file path (default: stdout)",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Print debug information to STDERR.",
        )

    def handle(self, *args, **options):
        course_id = options["course_id"]
        output_path = options["output"]
        debug = options["debug"]

        # Ensure the course exists
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            raise CommandError(f"Course with id={course_id} does not exist")

        if debug:
            self.stderr.write(
                f"[DEBUG] Course id={course_id}, name={course.name}, period={course.period}"
            )
            self.stderr.write("[DEBUG] Initializing students from course roster...")

        late_days_by_email: dict[str, int] = defaultdict(int)

        # You can add inactive_students here if you want:
        # students_qs = course.students.all() | course.inactive_students.all()
        students_qs = course.students.all()
        students_count = 0

        for student in students_qs:
            email = (student.email or "").strip()
            if not email:
                if debug:
                    self.stderr.write(
                        f"[DEBUG] Skipping student with no email: user_id={student.id}"
                    )
                continue
            late_days_by_email[email] = 0
            students_count += 1

        if debug:
            self.stderr.write(f"[DEBUG] Initialized {students_count} students from roster.")
            self.stderr.write("[DEBUG] Fetching submissions for this course...")

        submissions = (
            Submission.objects
            .filter(assignment__course_id=course_id)
            .select_related("assignment")
            .prefetch_related("students")
        )

        total_submissions = submissions.count()
        if debug:
            self.stderr.write(f"[DEBUG] Total submissions in course: {total_submissions}")

        late_submissions = 0
        inspected = 0  # just to limit debug spam

        for submission in submissions:
            assignment = submission.assignment
            due_at = assignment.uploadDueDate
            submitted_at = submission.dateUploaded

            # If either timestamp is missing, we can't calculate lateness
            if not due_at or not submitted_at:
                if debug and inspected < 30:
                    self.stderr.write(
                        f"[DEBUG] Submission {submission.id}: missing date(s) "
                        f"(uploadDueDate={due_at}, dateUploaded={submitted_at})"
                    )
                    inspected += 1
                continue

            # Make sure both are timezone-aware in same tz
            if timezone.is_naive(due_at):
                due_at = timezone.make_aware(due_at, timezone.get_current_timezone())
            if timezone.is_naive(submitted_at):
                submitted_at = timezone.make_aware(submitted_at, timezone.get_current_timezone())

            delta_seconds = (submitted_at - due_at).total_seconds()

            # On time or early
            if delta_seconds <= 0:
                if debug and inspected < 30:
                    self.stderr.write(
                        f"[DEBUG] Submission {submission.id}: ON TIME or early "
                        f"(due={due_at}, submitted={submitted_at}, "
                        f"delta_seconds={delta_seconds})"
                    )
                    inspected += 1
                continue

            days_late = math.ceil(delta_seconds / SECONDS_PER_DAY)
            late_submissions += 1

            # Debug some late submissions
            if debug and inspected < 30:
                self.stderr.write(
                    f"[DEBUG] Submission {submission.id}: LATE "
                    f"(due={due_at}, submitted={submitted_at}, "
                    f"delta_seconds={delta_seconds}, days_late={days_late})"
                )
                inspected += 1

            # Apply days_late to each student on the submission
            student_emails = []
            for student in submission.students.all():
                email = (student.email or "").strip()
                if not email:
                    if debug:
                        self.stderr.write(
                            f"[DEBUG] Submission {submission.id}: skipping student with no email "
                            f"(user_id={student.id})"
                        )
                    continue
                student_emails.append(email)

            if debug and student_emails and inspected < 30:
                self.stderr.write(
                    f"[DEBUG] Submission {submission.id}: applying {days_late} late days to {student_emails}"
                )
                inspected += 1

            for email in student_emails:
                if email not in late_days_by_email:
                    if debug:
                        self.stderr.write(
                            f"[DEBUG] Email {email} not in roster dict; adding with starting value 0."
                        )
                    late_days_by_email[email] = 0
                late_days_by_email[email] += days_late

        if debug:
            self.stderr.write(f"[DEBUG] Submissions with days_late > 0: {late_submissions}")
            self.stderr.write("[DEBUG] Final per-student tallies:")
            for email in sorted(late_days_by_email.keys()):
                self.stderr.write(f"[DEBUG]   {email} -> {late_days_by_email[email]} late days")

        # Write CSV
        if output_path == "-" or output_path is None:
            writer = csv.writer(self.stdout)
            self._write_csv(writer, late_days_by_email)
        else:
            with open(output_path, "w", newline="") as f:
                writer = csv.writer(f)
                self._write_csv(writer, late_days_by_email)

    def _write_csv(self, writer, late_days_by_email: dict[str, int]) -> None:
        writer.writerow(["user_email", "days_late"])
        for email in sorted(late_days_by_email.keys()):
            writer.writerow([email, late_days_by_email[email]])
