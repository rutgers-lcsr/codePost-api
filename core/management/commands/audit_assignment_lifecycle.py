# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Read-only audit of assignment lifecycle exposure.

Post-Phase-4 (isVisible/isReleased columns dropped) this reports on Assignment.state:
(1) submissions attached to assignments students cannot see (draft/archived) — historical
exposure artifacts from the pre-lifecycle bug, (2) submissions from students whose section
is hidden via hideFrom, (3) the state distribution, and (4) attached quizzes per state.

For the pre-migration legacy-boolean bucket audit, run this command from a checkout at or
before migration 0140 (tag: pre-lifecycle) against the un-migrated database.
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Max, Min, Q

from core.models import Assignment, Course, CourseAuditEvent, Submission


class Command(BaseCommand):
    help = (
        "STRICTLY READ-ONLY audit of assignment lifecycle exposure — never extend this "
        "command to mutate data (use set_assignment_state for fixes).\n"
        "Sections: submissions on student-invisible assignments; section-hidden (hideFrom) "
        "submissions; state distribution; quiz counts per state."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--course-id",
            type=int,
            default=None,
            help="Restrict the audit to a single Course.id.",
        )
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            default="-",
            help="Output file path for the exposed-assignment CSV (default: stdout)",
        )

    def handle(self, *args, **options):
        course_id = options["course_id"]
        output_path = options["output"]

        assignments = Assignment.objects.all()
        if course_id is not None:
            if not Course.objects.filter(pk=course_id).exists():
                raise CommandError(f"Course {course_id} does not exist.")
            assignments = assignments.filter(course_id=course_id)

        # ── 1. Submissions attached to assignments students cannot see ─────────────
        exposed = (
            assignments.filter(state__in=("draft", "archived"), submissions__isnull=False)
            .select_related("course", "course__organization")
            .annotate(
                sub_count=Count("submissions", distinct=True),
                student_sub_count=Count(
                    "submissions",
                    filter=Q(submissions__students__isnull=False),
                    distinct=True,
                ),
            )
            .distinct()
            .order_by("course_id", "id")
        )

        rows = []
        for a in exposed:
            subs = Submission.objects.filter(assignment=a).aggregate(
                first_upload=Min("dateUploaded"), last_upload=Max("dateUploaded")
            )
            student_count = (
                Submission.objects.filter(assignment=a)
                .values("students")
                .exclude(students=None)
                .distinct()
                .count()
            )
            rows.append({
                "org": getattr(a.course.organization, "shortname", ""),
                "course_id": a.course_id,
                "course": f"{a.course.name} {a.course.period}",
                "course_archived": a.course.archived,
                "assignment_id": a.id,
                "assignment": a.name,
                "state": a.state,
                "uploadDueDate": a.uploadDueDate,
                "partners": a.allowStudentUploadWithPartners,
                "submissions": a.sub_count,
                "submissions_with_students": a.student_sub_count,
                "distinct_students": student_count,
                "first_upload": subs["first_upload"],
                "last_upload": subs["last_upload"],
            })

        if output_path == "-":
            self._write_csv(self.stdout, rows)
        else:
            with open(output_path, "w", newline="") as f:
                self._write_csv(f, rows)

        audit_hits = CourseAuditEvent.objects.filter(
            event_type="submission_attempt",
            assignment__state__in=("draft", "archived"),
        )
        if course_id is not None:
            audit_hits = audit_hits.filter(course_id=course_id)

        self.stderr.write(
            f"[1] Student-invisible assignments with submissions: {len(rows)} assignment(s), "
            f"{sum(r['submissions'] for r in rows)} submission(s), "
            f"{audit_hits.count()} submission_attempt audit event(s)."
        )

        # ── 2. Section-hidden (hideFrom) exposure ────────────────────────────────────
        with_hidefrom = assignments.filter(hideFrom__isnull=False).distinct()
        section_rows = 0
        for a in with_hidefrom:
            leaked = (
                Submission.objects.filter(
                    assignment=a,
                    students__student_sections__in=a.hideFrom.all(),
                )
                .distinct()
                .count()
            )
            if leaked:
                section_rows += 1
                self.stderr.write(
                    f"    assignment {a.id} ({a.name}, course {a.course_id}): "
                    f"{leaked} submission(s) from section-hidden students"
                )
        self.stderr.write(
            f"[2] hideFrom: {with_hidefrom.count()} assignment(s) use it; "
            f"{section_rows} have submissions from hidden-section students."
        )

        # ── 3. State distribution (non-archived courses) ─────────────────────────────
        buckets = (
            assignments.filter(course__archived=False)
            .values("state")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        self.stderr.write("[3] State distribution — non-archived courses:")
        for b in buckets:
            self.stderr.write(f"    {b['state']}: {b['n']}")

        # ── 4. Attached quizzes per assignment state ─────────────────────────────────
        gated = (
            assignments.filter(quizzes__isnull=False)
            .values("state")
            .annotate(n=Count("quizzes", distinct=True))
            .order_by("-n")
        )
        self.stderr.write("[4] Attached quizzes per assignment state (availability opens at published/closed):")
        for b in gated:
            self.stderr.write(f"    {b['state']}: {b['n']} quiz(zes)")

    @staticmethod
    def _write_csv(out, rows):
        fieldnames = [
            "org", "course_id", "course", "course_archived", "assignment_id", "assignment",
            "state", "uploadDueDate", "partners", "submissions", "submissions_with_students",
            "distinct_students", "first_upload", "last_upload",
        ]
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
