# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Management command to pull an assignment (with rubric, submissions, files,
comments, and test results) from a remote codePost instance into the local
development database.

Usage:
    # Pull entire assignment (all submissions):
    python manage.py pull_production_data --assignment-id 123

    # Pull a single submission (and its parent assignment):
    python manage.py pull_production_data --submission-id 456

    # Pull assignment + only the first 5 submissions:
    python manage.py pull_production_data --assignment-id 123 --max-submissions 5

    # Put it on an existing local course (by local course ID):
    python manage.py pull_production_data --assignment-id 123 --course-id 1

    # Custom API key / host:
    python manage.py pull_production_data --assignment-id 123 \\
        --api-key "YOUR_KEY" \\
        --host "https://codepost-api.cs.rutgers.edu"

Requires the codepost-python SDK to be installed.
"""
from __future__ import annotations

import json
import logging
import pathlib
import urllib.request
import urllib.error
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    Assignment,
    AssignmentFile,
    Comment,
    Course,
    Organization,
    RubricCategory,
    RubricComment,
    Submission,
    SubmissionFile,
    User,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Pull an assignment and/or submission from a remote codePost instance "
        "into the local dev database. Requires CODEPOST_API_KEY env var or --api-key."
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--assignment-id",
            type=int,
            help="Remote assignment ID to pull.",
        )
        group.add_argument(
            "--submission-id",
            type=int,
            help="Remote submission ID to pull (will also pull its parent assignment).",
        )
        parser.add_argument(
            "--course-id",
            type=int,
            default=None,
            help="Local course ID to put the assignment into. If omitted, a course matching the remote name/period is created automatically.",
        )
        parser.add_argument(
            "--max-submissions",
            type=int,
            default=None,
            help="Maximum number of submissions to pull (default: all). Ignored when --submission-id is used.",
        )
        parser.add_argument(
            "--api-key",
            type=str,
            default=None,
            help="codePost API key. Falls back to CODEPOST_API_KEY env var.",
        )
        parser.add_argument(
            "--host",
            type=str,
            default="https://codepost-api.cs.rutgers.edu",
            help="Remote codePost API host.",
        )
        parser.add_argument(
            "--reset-submissions",
            action="store_true",
            default=False,
            help="Unfinalize all pulled submissions and remove their graders, so you can test grading from scratch.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            db_engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
            if "sqlite3" not in db_engine:
                raise CommandError(
                    "Refusing to run: DEBUG is off and the database is not SQLite. "
                    "This command is only intended for local development databases."
                )

        # Suppress Celery tasks (auto-detect, auto-execute) that fire on
        # model saves — avoids Redis connection errors in local dev.
        settings.CELERY_TASK_ALWAYS_EAGER = True
        settings.CELERY_TASK_EAGER_PROPAGATES = True
        try:
            from autograder.celery import app as celery_app
            celery_app.conf.task_always_eager = True
            celery_app.conf.task_eager_propagates = True
        except Exception:
            pass

        try:
            import importlib
            import codepost_api_client  # noqa: F401 # type: ignore[reportMissingImports] — verify the generated client is installed

            # The SDK's `codepost` package is shadowed by the Django project's
            # `codepost/` app, so we load the client module directly from the
            # installed SDK source using its file path.
            spec = importlib.util.find_spec("codepost_api_client")
            if spec is None or spec.origin is None:
                raise ImportError
            sdk_root = str(pathlib.Path(spec.origin).resolve().parent.parent / "codepost" / "client.py")
            client_spec = importlib.util.spec_from_file_location("codepost_sdk_client", sdk_root)
            if client_spec is None or client_spec.loader is None:
                raise ImportError
            client_module = importlib.util.module_from_spec(client_spec)
            client_spec.loader.exec_module(client_module)
            CodePost = client_module.CodePost  # noqa: N806
        except (ImportError, FileNotFoundError, AttributeError):
            raise CommandError(
                "codepost-python SDK is required. Install it with: pip install codepost"
            )

        api_key = options["api_key"]
        host = options["host"]

        try:
            client = CodePost(api_key=api_key, host=host)
        except ValueError as e:
            raise CommandError(str(e))

        self.client = client
        # Maps remote ID -> local instance for FK resolution
        self.rubric_comment_map: dict[int, RubricComment] = {}
        self.reset_submissions: bool = options.get("reset_submissions", False)

        # Resolve target course if specified
        self.target_course: Course | None = None
        if options["course_id"]:
            try:
                self.target_course = Course.objects.get(pk=options["course_id"])
            except Course.DoesNotExist:
                raise CommandError(f"Local course with id {options['course_id']} does not exist.")
            self.stdout.write(self.style.SUCCESS(
                f"Target course: {self.target_course.name} {self.target_course.period} (id={self.target_course.pk})"
            ))

        if options["submission_id"]:
            self._pull_submission_by_id(options["submission_id"])
        else:
            self._pull_assignment(options["assignment_id"], options["max_submissions"])

    # ──────────────────────────────────────────────────────────────────────
    # Top-level pull methods
    # ──────────────────────────────────────────────────────────────────────

    def _pull_submission_by_id(self, submission_id: int):
        """Pull a single submission and its parent assignment."""
        self.stdout.write(f"Fetching submission {submission_id} from remote...")
        remote_sub = self.client.submissions.retrieve(submission_id)
        remote_assignment_id = remote_sub.assignment

        local_assignment = self._pull_assignment_structure(remote_assignment_id)
        self._pull_submissions(remote_assignment_id, local_assignment, submission_ids=[submission_id])

    def _pull_assignment(self, assignment_id: int, max_submissions: int | None):
        """Pull an assignment and its submissions."""
        local_assignment = self._pull_assignment_structure(assignment_id)
        self._pull_submissions(assignment_id, local_assignment, max_submissions=max_submissions)

    # ──────────────────────────────────────────────────────────────────────
    # Assignment structure (course, assignment, rubric, files)
    # ──────────────────────────────────────────────────────────────────────

    def _pull_assignment_structure(self, assignment_id: int) -> Assignment:
        """Pull the assignment, its course, rubric, and assignment files."""
        self.stdout.write(f"Fetching assignment {assignment_id} from remote...")
        remote_assignment = self.client.assignments.retrieve(assignment_id)

        # Use explicitly provided course or auto-create one from remote
        local_course = self.target_course or self._ensure_course(remote_assignment.course)

        # Create or update the assignment
        local_assignment = self._create_assignment(remote_assignment, local_course)
        self.stdout.write(self.style.SUCCESS(
            f"  Assignment: {local_assignment.name} (local id={local_assignment.pk})"
        ))

        # Pull rubric
        self._pull_rubric(remote_assignment, local_assignment)

        # Pull assignment files
        self._pull_assignment_files(remote_assignment, local_assignment)

        return local_assignment

    def _ensure_course(self, course_id: int) -> Course:
        """Ensure the course exists locally, creating it if needed."""
        remote_course = self.client.courses.retrieve(course_id)

        # Get or create a default organization
        org, _ = Organization.objects.get_or_create(
            name="Imported",
            defaults={"shortname": "imported"},
        )

        local_course, created = Course.objects.update_or_create(
            name=remote_course.name,
            period=remote_course.period,
            organization=org,
            defaults={
                "archived": False,  # Always unarchived locally so we can edit
            },
        )
        verb = "Created" if created else "Found existing"
        self.stdout.write(self.style.SUCCESS(
            f"  {verb} course: {local_course.name} {local_course.period} (local id={local_course.pk})"
        ))
        return local_course

    def _create_assignment(self, remote: Any, local_course: Course) -> Assignment:
        """Create or update the assignment locally."""
        local, created = Assignment.objects.update_or_create(
            name=remote.name,
            course=local_course,
            defaults={
                "points": Decimal(str(remote.points)),
                "isReleased": remote.is_released or False,
                "feedbackReleased": remote.feedback_released or False,
                "allowStudentUpload": remote.allow_student_upload or False,
                "anonymousGrading": remote.anonymous_grading or False,
                "additiveGrading": remote.additive_grading or False,
                "sortKey": remote.sort_key or 0,
                "isVisible": remote.is_visible if remote.is_visible is not None else True,
                "forcedRubricMode": remote.forced_rubric_mode or False,
                "templateMode": remote.template_mode or False,
                "collaborativeRubricMode": remote.collaborative_rubric_mode or False,
                "liveFeedbackMode": remote.live_feedback_mode or False,
                "commentFeedback": remote.comment_feedback if remote.comment_feedback is not None else True,
                "hideGrades": remote.hide_grades or False,
                "allowRegradeRequests": remote.allow_regrade_requests or False,
            },
        )
        return local

    def _pull_rubric(self, remote_assignment: Any, local_assignment: Assignment):
        """Pull rubric categories and rubric comments."""
        for remote_cat_id in remote_assignment.rubric_categories:
            remote_cat = self.client.rubric.categories.retrieve(remote_cat_id)

            local_cat, _ = RubricCategory.objects.update_or_create(
                assignment=local_assignment,
                name=remote_cat.name,
                defaults={
                    "pointLimit": remote_cat.point_limit,
                    "sortKey": remote_cat.sort_key or 0,
                    "helpText": remote_cat.help_text or "",
                    "atMostOnce": remote_cat.at_most_once or False,
                },
            )

            for remote_rc_id in remote_cat.rubric_comments:
                remote_rc = self.client.rubric.comments.retrieve(remote_rc_id)
                local_rc, _ = RubricComment.objects.update_or_create(
                    category=local_cat,
                    text=remote_rc.text or "",
                    defaults={
                        "pointDelta": Decimal(str(remote_rc.point_delta)),
                        "sortKey": remote_rc.sort_key or 0,
                        "explanation": remote_rc.explanation or "",
                        "instructionText": remote_rc.instruction_text or "",
                        "templateTextOn": remote_rc.template_text_on or False,
                        "name": remote_rc.name,
                    },
                )
                self.rubric_comment_map[remote_rc_id] = local_rc

        cat_count = local_assignment.rubricCategories.count()
        rc_count = RubricComment.objects.filter(category__assignment=local_assignment).count()
        self.stdout.write(self.style.SUCCESS(
            f"  Rubric: {cat_count} categories, {rc_count} comments"
        ))

    def _pull_assignment_files(self, remote_assignment: Any, local_assignment: Assignment):
        """Pull assignment-level template files."""
        for remote_file_id in remote_assignment.files:
            remote_file = self.client.assignments.files.retrieve(remote_file_id)
            AssignmentFile.objects.update_or_create(
                assignment=local_assignment,
                name=remote_file.name,
                defaults={
                    "data": remote_file.data or "",
                    "extension": remote_file.extension,
                    "path": remote_file.path or "",
                },
            )
        self.stdout.write(self.style.SUCCESS(
            f"  Assignment files: {len(remote_assignment.files)}"
        ))

    # ──────────────────────────────────────────────────────────────────────
    # Submissions
    # ──────────────────────────────────────────────────────────────────────

    def _list_submissions_for_assignment(self, assignment_id: int) -> list[Any]:
        """Fetch all submissions for an assignment via direct HTTP.

        The SDK's list_all() expects a paginated response, but the
        assignments/{id}/submissions/ endpoint may return a flat list.
        This bypasses the SDK deserialization to handle both cases.
        """
        host = self.client._api_client.configuration.host.rstrip("/")
        api_key = list(self.client._api_client.configuration.api_key.values())[0]
        prefix = list(self.client._api_client.configuration.api_key_prefix.values())[0]

        all_results: list[dict[str, Any]] = []
        url = f"{host}/assignments/{assignment_id}/submissions/"

        while url:
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"{prefix} {api_key}")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())

            if isinstance(data, list):
                # Non-paginated flat list
                all_results.extend(data)
                url = None
            elif isinstance(data, dict) and "results" in data:
                # Paginated response
                all_results.extend(data["results"])
                url = data.get("next")
            else:
                raise CommandError(f"Unexpected response format from submissions endpoint: {type(data)}")

        # Convert dicts to simple namespace objects for consistent attribute access
        from types import SimpleNamespace

        def _to_ns(d: dict[str, Any]) -> SimpleNamespace:
            """Convert a camelCase API dict to a snake_case SimpleNamespace."""
            mapping = {
                "isFinalized": "is_finalized",
                "dateEdited": "date_edited",
                "queueOrderKey": "queue_order_key",
                "dateUploaded": "date_uploaded",
                "testRunsCompleted": "test_runs_completed",
                "lateDayCreditsUsed": "late_day_credits_used",
                "hiddenBeforePublish": "hidden_before_publish",
                "pointDelta": "point_delta",
                "startChar": "start_char",
                "endChar": "end_char",
                "startLine": "start_line",
                "endLine": "end_line",
                "rubricComment": "rubric_comment",
            }
            ns = SimpleNamespace()
            for key, val in d.items():
                attr = mapping.get(key, key)
                if attr == "files" and isinstance(val, list) and val and isinstance(val[0], dict):
                    val = [_to_ns(f) for f in val]
                ns.__dict__[attr] = val
            return ns

        return [_to_ns(r) for r in all_results]

    def _pull_submissions(
        self,
        remote_assignment_id: int,
        local_assignment: Assignment,
        *,
        submission_ids: list[int] | None = None,
        max_submissions: int | None = None,
    ):
        """Pull submissions (with files and comments) into the local DB."""
        if submission_ids:
            remote_subs = [self.client.submissions.retrieve(sid) for sid in submission_ids]
        else:
            remote_subs = self._list_submissions_for_assignment(remote_assignment_id)

        if max_submissions is not None:
            remote_subs = remote_subs[:max_submissions]

        total = len(remote_subs)
        self.stdout.write(f"Pulling {total} submission(s)...")

        for i, remote_sub in enumerate(remote_subs, 1):
            self._pull_single_submission(remote_sub, local_assignment, i, total)

        self.stdout.write(self.style.SUCCESS(f"\nDone! Pulled {total} submission(s)."))

    def _pull_single_submission(
        self, remote_sub: Any, local_assignment: Assignment, index: int, total: int
    ):
        """Pull a single submission with its files and comments."""
        course = local_assignment.course

        # Ensure student users exist locally and add to course roster
        student_emails = [s for s in (remote_sub.students or []) if s]
        local_students = []
        for email in student_emails:
            user, _ = User.objects.get_or_create(
                username=email,
                defaults={"email": email},
            )
            local_students.append(user)
            if not course.students.filter(pk=user.pk).exists():
                course.students.add(user)

        # Ensure grader user exists locally and add to course roster
        local_grader = None
        if remote_sub.grader:
            local_grader, _ = User.objects.get_or_create(
                username=remote_sub.grader,
                defaults={"email": remote_sub.grader},
            )
            if not course.graders.filter(pk=local_grader.pk).exists():
                course.graders.add(local_grader)

        if self.reset_submissions:
            local_grader = None

        with transaction.atomic():
            local_sub = Submission.objects.create(
                assignment=local_assignment,
                grader=local_grader,
                isFinalized=False if self.reset_submissions else (remote_sub.is_finalized or False),
                grade=None if self.reset_submissions else (Decimal(str(remote_sub.grade)) if remote_sub.grade is not None else None),
            )
            # Set M2M students
            if local_students:
                local_sub.students.set(local_students)

            # Pull files and their comments
            file_count = 0
            comment_count = 0
            for remote_file in (remote_sub.files or []):
                local_file, fc, cc = self._pull_submission_file(remote_file, local_sub)
                file_count += fc
                comment_count += cc

        students_str = ", ".join(student_emails) if student_emails else "(no students)"
        self.stdout.write(
            f"  [{index}/{total}] Submission for {students_str}: "
            f"{file_count} file(s), {comment_count} comment(s)"
        )

    def _pull_submission_file(
        self, remote_file: Any, local_sub: Submission
    ) -> tuple[SubmissionFile, int, int]:
        """Pull a single submission file and its comments."""
        local_file = SubmissionFile.objects.create(
            submission=local_sub,
            name=remote_file.name,
            data=remote_file.data or "",
            extension=remote_file.extension,
            path=remote_file.path or "",
        )

        # Pull comments for this file
        comment_count = 0
        for remote_comment_id in (remote_file.comments or []):
            remote_comment = self.client.comments.retrieve(remote_comment_id)
            self._create_comment(remote_comment, local_file)
            comment_count += 1

        return local_file, 1, comment_count

    def _create_comment(self, remote_comment: Any, local_file: SubmissionFile):
        """Create a comment on a local file."""
        # Resolve rubric comment if linked
        local_rubric_comment = None
        if remote_comment.rubric_comment:
            local_rubric_comment = self.rubric_comment_map.get(remote_comment.rubric_comment)

        # Ensure author exists
        author_email = remote_comment.author or "unknown@imported.dev"
        author, _ = User.objects.get_or_create(
            username=author_email,
            defaults={"email": author_email},
        )

        Comment.objects.create(
            file=local_file,
            text=remote_comment.text or "",
            pointDelta=Decimal(str(remote_comment.point_delta)) if remote_comment.point_delta is not None else None,
            startChar=remote_comment.start_char or 0,
            endChar=remote_comment.end_char or 0,
            startLine=remote_comment.start_line,
            endLine=remote_comment.end_line if remote_comment.end_line is not None else remote_comment.start_line,
            rubricComment=local_rubric_comment,
            author=author,
            feedback=remote_comment.feedback or 0,
            color=remote_comment.color or None,
        )
