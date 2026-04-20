# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Management command to run the full submission pipeline for all submissions
in an assignment — mimicking what happens when a student submits.

This triggers:
  1. File execution + caching (Phase 1 of RunSubmission)
  2. Test execution (Phase 2 of RunSubmission)
  3. AI grading assistance: suggested comments + submission summary

Usage:
    # Run all submissions for an assignment:
    python manage.py run_submissions --assignment-id 143

    # Skip file/test execution, only run AI generation:
    python manage.py run_submissions --assignment-id 143 --ai-only

    # Skip AI generation, only run file/test execution:
    python manage.py run_submissions --assignment-id 143 --no-ai

    # Run a single submission:
    python manage.py run_submissions --submission-id 420

    # Limit to first N submissions:
    python manage.py run_submissions --assignment-id 143 --max-submissions 5

    # Run with higher concurrency (default: 4):
    python manage.py run_submissions --assignment-id 143 --concurrency 8
"""
from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import (
    AIUsageRecord,
    Assignment,
    Submission,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Run the full submission pipeline (execution + AI) for all submissions "
        "in an assignment, mimicking the student submission flow."
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--assignment-id",
            type=int,
            help="Local assignment ID whose submissions to process.",
        )
        group.add_argument(
            "--submission-id",
            type=int,
            help="Single local submission ID to process.",
        )
        parser.add_argument(
            "--max-submissions",
            type=int,
            default=None,
            help="Maximum number of submissions to process (default: all).",
        )
        parser.add_argument(
            "--ai-only",
            action="store_true",
            default=False,
            help="Skip file/test execution and only run AI generation.",
        )
        parser.add_argument(
            "--no-ai",
            action="store_true",
            default=False,
            help="Skip AI generation and only run file/test execution.",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=4,
            help="Number of submissions to process in parallel (default: 4).",
        )

    def handle(self, *args, **options):
        # Configure Celery for eager (synchronous) execution
        settings.CELERY_TASK_ALWAYS_EAGER = True
        settings.CELERY_TASK_EAGER_PROPAGATES = True
        try:
            from autograder.celery import app as celery_app
            celery_app.conf.task_always_eager = True
            celery_app.conf.task_eager_propagates = True
        except Exception:
            pass

        ai_only = options["ai_only"]
        no_ai = options["no_ai"]
        if ai_only and no_ai:
            raise CommandError("Cannot use --ai-only and --no-ai together.")

        # Resolve submissions
        if options["submission_id"]:
            try:
                submission = Submission.objects.select_related(
                    "assignment", "assignment__course"
                ).get(pk=options["submission_id"])
            except Submission.DoesNotExist:
                raise CommandError(f"Submission {options['submission_id']} not found.")
            submissions = [submission]
            assignment = submission.assignment
        else:
            try:
                assignment = Assignment.objects.select_related("course").get(
                    pk=options["assignment_id"]
                )
            except Assignment.DoesNotExist:
                raise CommandError(f"Assignment {options['assignment_id']} not found.")
            submissions = list(
                assignment.submissions.select_related("assignment", "assignment__course")
                .order_by("pk")
            )

        if options["max_submissions"]:
            submissions = submissions[: options["max_submissions"]]

        total = len(submissions)
        if total == 0:
            self.stdout.write(self.style.WARNING("No submissions to process."))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Assignment: {assignment.name} (id={assignment.pk}), "
            f"Course: {assignment.course.name} {assignment.course.period}"
        ))

        concurrency = options["concurrency"]
        self.stdout.write(f"Processing {total} submission(s) with concurrency={concurrency}...\n")

        asyncio.run(self._ahandle(submissions, assignment, ai_only, no_ai, concurrency))

    async def _ahandle(
        self,
        submissions: list[Submission],
        assignment: Assignment,
        ai_only: bool,
        no_ai: bool,
        concurrency: int,
    ):
        """Async entry point — processes submissions concurrently."""
        total = len(submissions)
        cost_before = await asyncio.to_thread(self._get_ai_cost, assignment)
        sem = asyncio.Semaphore(concurrency)
        completed = 0

        async def process_one(idx: int, sub: Submission) -> dict[str, Any]:
            nonlocal completed
            async with sem:
                students = await asyncio.to_thread(
                    lambda: ", ".join(sub.students.values_list("email", flat=True)) or "(no students)"
                )
                sub_start = time.time()
                exec_result = None
                ai_result = None

                if not ai_only:
                    exec_result = await asyncio.to_thread(self._run_execution, sub)
                if not no_ai:
                    ai_result = await asyncio.to_thread(self._run_ai_generation, sub)

                elapsed = time.time() - sub_start
                completed += 1
                self.stderr.write(f"  [{completed}/{total}] done\r")
                return {
                    "idx": idx,
                    "sub": sub,
                    "students": students,
                    "exec_result": exec_result,
                    "ai_result": ai_result,
                    "elapsed": elapsed,
                }

        wall_start = time.time()
        results = await asyncio.gather(
            *(process_one(i, sub) for i, sub in enumerate(submissions, 1))
        )
        wall_time = time.time() - wall_start

        # Print results in submission order
        exec_success = exec_fail = ai_success = ai_fail = ai_skip = 0
        for r in results:
            self.stdout.write(f"[{r['idx']}/{total}] Submission {r['sub'].pk} ({r['students']})")
            if r["exec_result"] is not None:
                result = r["exec_result"]
                if result["success"]:
                    exec_success += 1
                    detail = result.get("message", "")
                    if result.get("files_processed"):
                        detail = f"{result['files_processed']} file(s) executed"
                    if result.get("tests_run"):
                        detail += f", {result['tests_run']} test(s) run"
                    self.stdout.write(f"  Execution: {self.style.SUCCESS('OK')} {detail}")
                else:
                    exec_fail += 1
                    self.stdout.write(f"  Execution: {self.style.ERROR('FAILED')} {result.get('error', '')}")
            if r["ai_result"] is not None:
                ai_res = r["ai_result"]
                if ai_res == "success":
                    ai_success += 1
                    self.stdout.write(f"  AI generation: {self.style.SUCCESS('OK')}")
                elif ai_res == "skipped":
                    ai_skip += 1
                    self.stdout.write(f"  AI generation: {self.style.WARNING('SKIPPED')} (not configured)")
                else:
                    ai_fail += 1
                    self.stdout.write(f"  AI generation: {self.style.ERROR('FAILED')} {ai_res}")
            self.stdout.write(f"  Time: {r['elapsed']:.1f}s\n")

        # Cost summary
        cost_after = await asyncio.to_thread(self._get_ai_cost, assignment)
        run_cost = cost_after - cost_before

        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS(f"Done! Processed {total} submission(s) in {wall_time:.1f}s"))
        if not ai_only:
            self.stdout.write(f"  Execution: {exec_success} succeeded, {exec_fail} failed")
        if not no_ai:
            self.stdout.write(f"  AI generation: {ai_success} succeeded, {ai_fail} failed, {ai_skip} skipped")
        self.stdout.write(f"\n  AI cost this run: ${run_cost:.6f}")
        self.stdout.write(f"  Total AI cost for assignment: ${cost_after:.6f}")
        await asyncio.to_thread(self._print_ai_usage_breakdown, assignment, cost_before)

    def _run_execution(self, submission: Submission) -> dict[str, Any]:
        """Run file execution + tests for a single submission."""
        try:
            from autograder.run import RunSubmission
            from core.models import Environment
        except ImportError:
            return {"success": False, "error": "autograder app not available"}

        try:
            Environment.objects.get(assignment_id=submission.assignment_id)
        except Environment.DoesNotExist:
            return {"success": False, "error": "No environment configured"}

        try:
            result = RunSubmission(submission.id)
            if result is None:
                result = {}
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run_ai_generation(self, submission: Submission) -> str:
        """Run AI suggestion + summary generation. Returns 'success', 'skipped', or error string."""
        try:
            from core.services.ai_service import AIService

            course = submission.assignment.course
            service = AIService(course, submission.assignment)

            if not service.is_configured:
                return "skipped"
            if service.is_globally_disabled:
                return "skipped"

            # Run the task function directly (not .delay()) since we're in eager mode
            from core.tasks import generate_ai_grading_assistance
            generate_ai_grading_assistance(submission.id)
            return "success"
        except Exception as e:
            return str(e)

    def _get_ai_cost(self, assignment: Assignment) -> Decimal:
        """Get total AI cost for an assignment."""
        result = AIUsageRecord.objects.filter(
            assignment=assignment
        ).aggregate(total=models_Sum("estimated_cost"))
        return result["total"] or Decimal("0")

    def _print_ai_usage_breakdown(self, assignment: Assignment, cost_before: Decimal):
        """Print a breakdown of AI usage by request type for this run."""
        from django.db.models import Sum, Count

        records = (
            AIUsageRecord.objects.filter(assignment=assignment)
            .values("request_type", "provider", "model")
            .annotate(
                count=Count("id"),
                total_input=Sum("input_tokens"),
                total_output=Sum("output_tokens"),
                total_cached=Sum("cached_tokens"),
                total_cost=Sum("estimated_cost"),
            )
            .order_by("request_type")
        )

        if not records:
            return

        self.stdout.write(f"\n  {'Type':<25} {'Provider':<10} {'Model':<25} {'Count':>5} {'Input':>10} {'Output':>10} {'Cached':>10} {'Cost':>12}")
        self.stdout.write(f"  {'-'*25} {'-'*10} {'-'*25} {'-'*5} {'-'*10} {'-'*10} {'-'*10} {'-'*12}")
        for r in records:
            self.stdout.write(
                f"  {r['request_type']:<25} {r['provider']:<10} {r['model']:<25} "
                f"{r['count']:>5} {r['total_input']:>10} {r['total_output']:>10} "
                f"{r['total_cached']:>10} ${r['total_cost']:>11.6f}"
            )


# Import Sum at module level to avoid issues
from django.db.models import Sum as models_Sum
