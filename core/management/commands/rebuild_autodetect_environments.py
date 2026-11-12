# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
One-time rebuild of auto-detect environments so every image matches its package list.

Before package lists existed, `requirements` was rewritten on each submission with no
rebuild, so the listed packages and the built image drifted apart. For each auto-detect
environment this command:

  1. re-detects packages from the instructor's assignment files and test scripts,
  2. (python, r) seeds the learned list with packages at least three distinct submissions
     needed: from the run counts already recorded, and from the imports in submitted files,
  3. builds the image, one environment at a time, in this process.

It needs Docker, so run it on a worker, outside grading hours:

    docker exec codepost-worker python manage.py rebuild_autodetect_environments --dry-run
    docker exec codepost-worker python manage.py rebuild_autodetect_environments
    docker exec codepost-worker python manage.py rebuild_autodetect_environments --env 77 --env 107
"""
from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from autograder.run import BuildEnvironment
from autograder.services import environment_packages as packages
from autograder.services.autodetector import Autodetector
from autograder.services.converger import Converger
from core.constants import NON_CODE_EXTENSIONS
from core.models import Environment, SubmissionFile
from core.services.file_handlers.factory import FileHandlerFactory


class Command(BaseCommand):
    help = "Rebuild auto-detect environments once so their images match their package lists."

    def add_arguments(self, parser):
        parser.add_argument("--env", type=int, action="append", dest="env_ids",
                            help="Only this environment id (repeatable). Default: all auto-detect environments.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would change for each environment; write and build nothing.")

    def handle(self, *args, **options):
        envs = Environment.objects.filter(auto_detect=True).exclude(language="").order_by("id")
        if options["env_ids"]:
            envs = envs.filter(id__in=options["env_ids"])

        built, failed, skipped = [], [], []
        for env in envs.select_related("assignment"):
            label = f"env {env.id} (assignment {env.assignment.id}, {env.language})"
            if env.build_status == 1:
                self.stdout.write(f"{label}: build in progress, skipped")
                skipped.append(env.id)
                continue

            before = env.requirements or ""
            with transaction.atomic():
                Autodetector.detect_and_update(assignment=env.assignment, force=True)
                env.refresh_from_db()
                seeds = self._seed_learned_packages(env)
                after = env.requirements or ""
                if options["dry_run"]:
                    transaction.set_rollback(True)

            self.stdout.write(f"{label}:")
            self.stdout.write(f"  listed before: {before.replace(chr(10), ', ') or '(none)'}")
            self.stdout.write(f"  listed after:  {after.replace(chr(10), ', ') or '(none)'}")
            if seeds:
                self.stdout.write(f"  learned from submissions: {', '.join(sorted(seeds))}")
            if options["dry_run"]:
                continue

            result = BuildEnvironment(env.id, reason="one-time rebuild")
            if not result.get("success") and seeds:
                # A seeded package may be what broke the build; the image matters more.
                self.stdout.write(self.style.WARNING("  build failed; retrying without the learned packages"))
                env.refresh_from_db()
                env.learned_packages = [p for p in env.learned_packages or [] if p not in seeds]
                packages.refresh_requirements(env)
                env.save(update_fields=["learned_packages", "requirements"])
                result = BuildEnvironment(env.id, reason="one-time rebuild")

            if result.get("success"):
                self.stdout.write(self.style.SUCCESS(f"  built {result.get('image')}"))
                built.append(env.id)
            else:
                self.stdout.write(self.style.ERROR(f"  build failed: {result.get('error')}"))
                failed.append(env.id)

        if options["dry_run"]:
            self.stdout.write("Dry run: nothing was written or built.")
            return
        self.stdout.write(f"Built {len(built)}, failed {len(failed)} {failed or ''}, skipped {len(skipped)} {skipped or ''}")

    def _seed_learned_packages(self, env: Environment) -> set:
        """Add to env.learned_packages what enough distinct submissions needed. Saves env."""
        converger = Converger.get_converger(env.language)
        if not packages.supports_package_list(env.language) or converger is None:
            return set()

        needed_by = defaultdict(set)
        for name, entry in (env.convergence_stats or {}).items():
            if isinstance(entry, dict) and not entry.get("status"):
                needed_by[name].update(entry.get("submissions") or [])

        family = packages.language_family(env.language)
        files = SubmissionFile.objects.filter(submission__assignment=env.assignment)
        for f in files.iterator():
            if f.extension in NON_CODE_EXTENSIONS:
                continue
            try:
                handler = FileHandlerFactory.get_handler(f)
                if packages.language_family(handler.get_language()) != family:
                    continue
                for package in (handler.get_requirements() or "").split("\n"):
                    if package.strip():
                        needed_by[package.strip()].add(f.submission_id)
            except Exception:
                continue

        listed = packages._keys(env.language, packages._lines(env.requirements))
        listed |= packages._keys(env.language, env.excluded_packages)
        local = Autodetector.collect_local_modules(list(env.assignment.files.all()))
        seeds = set()
        for package, submissions in needed_by.items():
            if len(submissions) < converger.MODULE_THRESHOLD or package in local:
                continue
            if packages.package_key(env.language, package) in listed or not converger._is_valid_module(package):
                continue
            if family == "python" and not Autodetector.check_pypi_existence(package):
                continue
            seeds.add(package)

        if seeds:
            env.learned_packages = sorted(set(env.learned_packages or []) | seeds)
            env.convergence_stats = {name: entry for name, entry in (env.convergence_stats or {}).items()
                                     if name not in seeds}
            packages.refresh_requirements(env)
            env.save(update_fields=["learned_packages", "convergence_stats", "requirements"])
        return seeds
