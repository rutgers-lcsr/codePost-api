import base64
import json
from pathlib import Path
from typing import Any, Iterable
from typing import cast

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Assignment, AssignmentDataSet, AssignmentFile, Course, Environment, Submission, SubmissionFile


DEFAULT_UI_SEED_FILE = (
    Path(__file__).resolve().parents[4]
    / "codePost-ui"
    / "src"
    / "__tests__"
    / "test_submission"
    / "backend_seed_data.json"
)

LANGUAGE_FIELD = cast(Any, Environment._meta.get_field("language"))
ALLOWED_ENV_LANGUAGES = {choice[0] for choice in LANGUAGE_FIELD.choices}


def _decode_content(file_payload: dict[str, Any]) -> str:
    encoding = file_payload.get("encoding", "utf-8")
    content = file_payload.get("content", "")

    if encoding == "base64":
        try:
            return base64.b64decode(content).decode("utf-8")
        except Exception:
            # SubmissionFile/AssignmentFile are text-backed, so we degrade gracefully.
            return base64.b64decode(content).decode("utf-8", errors="replace")

    return str(content)


def _extension_from_name(file_name: str) -> str:
    suffix = Path(file_name).suffix
    return suffix if suffix else ".txt"


class Command(BaseCommand):
    help = (
        "Seed a course with language compatibility assignments and fake submissions "
        "from backend_seed_data.json generated in codePost-ui."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--course-id",
            type=int,
            required=True,
            help="Course.id to seed assignments/submissions into.",
        )
        parser.add_argument(
            "--seed-file",
            type=str,
            default=str(DEFAULT_UI_SEED_FILE),
            help="Path to backend_seed_data.json file.",
        )
        parser.add_argument(
            "--languages",
            type=str,
            default="",
            help="Optional comma-separated language keys to seed (e.g. python,node,java).",
        )
        parser.add_argument(
            "--replace-existing",
            action="store_true",
            help="Delete existing assignments with the same names in target course before seeding.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and print actions without writing to database.",
        )

    def handle(self, *args, **options):
        course_id: int = options["course_id"]
        dry_run: bool = options["dry_run"]
        replace_existing: bool = options["replace_existing"]
        seed_file_path = Path(options["seed_file"]).expanduser().resolve()

        language_filter = {
            value.strip()
            for value in options["languages"].split(",")
            if value.strip()
        }

        if not seed_file_path.exists():
            raise CommandError(f"Seed file does not exist: {seed_file_path}")

        try:
            payload = json.loads(seed_file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in seed file: {exc}") from exc

        assignments_payload = payload.get("assignments")
        if not isinstance(assignments_payload, list):
            raise CommandError("Seed file missing 'assignments' array.")

        try:
            course = Course.objects.select_related("organization").get(id=course_id)
        except Course.DoesNotExist as exc:
            raise CommandError(f"Course with id={course_id} does not exist") from exc

        filtered_assignments = [
            item for item in assignments_payload if not language_filter or item.get("key") in language_filter
        ]

        if language_filter and not filtered_assignments:
            raise CommandError("No assignments matched --languages filter.")

        self.stdout.write(
            f"Target course: {course.id} ({course.name} {course.period}) | "
            f"Assignments selected: {len(filtered_assignments)}"
        )

        if dry_run:
            self._print_plan(filtered_assignments)
            self.stdout.write(self.style.WARNING("Dry run only: no database writes performed."))
            return

        created_assignments = 0
        skipped_assignments = 0
        created_submissions = 0
        created_assignment_files = 0
        created_datasets = 0
        created_submission_files = 0

        with transaction.atomic():
            for assignment_item in filtered_assignments:
                assignment_name = assignment_item.get("assignmentName")
                language_key = assignment_item.get("key")
                if not assignment_name or not language_key:
                    raise CommandError("Each assignment entry must include 'key' and 'assignmentName'.")

                existing_qs = Assignment.objects.filter(course=course, name=assignment_name)
                if existing_qs.exists() and not replace_existing:
                    skipped_assignments += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping existing assignment '{assignment_name}' (use --replace-existing to recreate)."
                        )
                    )
                    continue

                if existing_qs.exists() and replace_existing:
                    deleted_count, _ = existing_qs.delete()
                    self.stdout.write(
                        self.style.WARNING(
                            f"Deleted existing assignment '{assignment_name}' ({deleted_count} related rows removed)."
                        )
                    )

                assignment = Assignment.objects.create(
                    course=course,
                    name=assignment_name,
                    points=100,
                    isVisible=True,
                    isReleased=True,
                    feedbackReleased=True,
                    allowStudentUpload=False,
                    sortKey=Assignment.objects.filter(course=course).count(),
                )
                created_assignments += 1

                environment_language = assignment_item.get("environmentLanguage") or "python-3.12"
                if environment_language not in ALLOWED_ENV_LANGUAGES:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Unknown environment language '{environment_language}' for {assignment_name}; "
                            "falling back to python-3.12."
                        )
                    )
                    environment_language = "python-3.12"

                Environment.objects.create(
                    assignment=assignment,
                    language=environment_language,
                )

                assignment_files = assignment_item.get("assignmentFiles") or []
                for file_payload in assignment_files:
                    created_assignment_files += 1
                    AssignmentFile.objects.create(
                        assignment=assignment,
                        name=file_payload.get("name", "unnamed.txt"),
                        path=file_payload.get("path") or None,
                        extension=_extension_from_name(file_payload.get("name", "")),
                        data=_decode_content(file_payload),
                        required=False,
                        description="Seeded compatibility template file",
                    )

                assignment_datasets = assignment_item.get("assignmentDataSets") or []
                for dataset_payload in assignment_datasets:
                    dataset_name = dataset_payload.get("name") or "seed_resource.txt"
                    dataset_data = _decode_content(dataset_payload)
                    mount_path = dataset_payload.get("mountPath") or f"shared/{dataset_name}"

                    data_set = AssignmentDataSet(
                        assignment=assignment,
                        name=dataset_name,
                        description=dataset_payload.get("description")
                        or "Seeded execution resource dataset",
                        mount_path=mount_path,
                        is_active=True,
                        hidden=False,
                    )
                    data_set.file.save(dataset_name, ContentFile(dataset_data.encode("utf-8")), save=True)
                    created_datasets += 1

                fake_submissions = assignment_item.get("fakeSubmissions") or []
                for submission_index, submission_payload in enumerate(fake_submissions, start=1):
                    scenario_key = submission_payload.get("key") or f"{language_key}_submission_{submission_index}"
                    student = self._get_or_create_seed_student(
                        course=course,
                        language_key=str(language_key),
                        scenario_key=str(scenario_key),
                    )

                    submission = Submission.objects.create(
                        assignment=assignment,
                        isFinalized=False,
                        dateUploaded=timezone.now(),
                    )
                    submission.students.add(student.pk)
                    created_submissions += 1

                    files = submission_payload.get("files") or []
                    for file_payload in files:
                        created_submission_files += 1
                        SubmissionFile.objects.create(
                            submission=submission,
                            name=file_payload.get("name", "unnamed.txt"),
                            path=file_payload.get("path") or None,
                            extension=_extension_from_name(file_payload.get("name", "")),
                            data=_decode_content(file_payload),
                        )

        self.stdout.write(self.style.SUCCESS("Seeding complete."))
        self.stdout.write(f"Assignments created: {created_assignments}")
        self.stdout.write(f"Assignments skipped: {skipped_assignments}")
        self.stdout.write(f"Template files created: {created_assignment_files}")
        self.stdout.write(f"Datasets created: {created_datasets}")
        self.stdout.write(f"Submissions created: {created_submissions}")
        self.stdout.write(f"Submission files created: {created_submission_files}")

    def _print_plan(self, assignments_payload: Iterable[dict[str, Any]]) -> None:
        for item in assignments_payload:
            assignment_name = item.get("assignmentName", "<missing-name>")
            language_key = item.get("key", "<missing-key>")
            template_count = len(item.get("assignmentFiles") or [])
            dataset_count = len(item.get("assignmentDataSets") or [])
            submission_count = len(item.get("fakeSubmissions") or [])
            self.stdout.write(
                f"- {language_key}: '{assignment_name}' | template files={template_count} | datasets={dataset_count} | fake submissions={submission_count}"
            )

    def _get_or_create_seed_student(self, course: Course, language_key: str, scenario_key: str) -> User:
        normalized_key = scenario_key.lower().replace("/", "_").replace(" ", "_")
        username = f"seed_{language_key}_{normalized_key}"[:150]
        email = f"{username}@seed.local"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_active": True,
            },
        )

        if created:
            user.set_password("rootabega")
            user.save()

        profile = getattr(user, "profile", None)
        if profile is not None and profile.organization_id != course.organization.id:
            profile.organization = course.organization
            profile.save()

        if not course.students.filter(pk=user.pk).exists():
            course.students.add(user.pk)

        return user
