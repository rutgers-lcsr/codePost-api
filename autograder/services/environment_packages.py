# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Package lists of an auto-detect environment.

For line-oriented languages (python, r) `Environment.requirements` is never edited directly.
It is always recomputed from four lists, each with one writer:

- detected_requirements: the Autodetector, from the instructor's assignment files and test scripts
- learned_packages:      the Converger, once enough distinct submissions needed a package at run time
- pinned_packages:       the instructor (a requirement line, so it may carry a version)
- excluded_packages:     the instructor; an excluded name stays out whatever detects or learns it

requirements = detected + learned + pinned - excluded. A pinned line wins over a detected or
learned line for the same package. `built_requirements` records what the current image was
built from, so "image out of date" is `built_requirements != requirements`.

Whole-file manifests (package.json, pom.xml, ...) are not covered: those languages keep
their single `requirements` blob.
"""
import logging
import re
from datetime import timedelta
from typing import Any, Dict, List

from django.db.models import Q
from django.utils import timezone

from autograder.services.autodetector import Autodetector, LINE_ORIENTED_FAMILIES
from core.models import Environment

logger = logging.getLogger(__name__)

# An automatic rebuild waits this long so a burst of changes becomes one build ...
REBUILD_DEBOUNCE_SECONDS = 30
# ... and learned or re-detected packages rebuild an environment at most this often.
REBUILD_MIN_INTERVAL = timedelta(minutes=10)
# A queued rebuild this far past due was lost (worker died, broker flushed); allow a new one.
REBUILD_CLAIM_EXPIRY = timedelta(minutes=30)

_NAME = r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?'
_VERSION_CLAUSE = r'(?:==|>=|<=|~=|!=|<|>)[A-Za-z0-9.*+!_-]+'
_PYTHON_REQUIREMENT = re.compile(
    rf'^{_NAME}(?:\[[A-Za-z0-9,._-]+\])?(?:{_VERSION_CLAUSE}(?:,{_VERSION_CLAUSE})*)?$')
_R_PACKAGE = re.compile(r'^[A-Za-z][A-Za-z0-9.]*$')


class InvalidPackage(ValueError):
    """The text is not a package an instructor can add; the message is safe to show them."""


def language_family(language: str) -> str:
    return (language or '').lower().split('-')[0]


def supports_package_list(language: str) -> bool:
    return language_family(language) in LINE_ORIENTED_FAMILIES


def package_name(line: str) -> str:
    """'numpy>=1.26' -> 'numpy'."""
    match = re.match(_NAME, (line or '').strip())
    return match.group(0) if match else ''


def package_key(language: str, line: str) -> str:
    """What makes two lines the same package: PyPI names ignore case and -_. differences."""
    name = package_name(line)
    if language_family(language) == 'python':
        return re.sub(r'[-_.]+', '-', name).lower()
    return name


def _lines(text: str) -> List[str]:
    return [line.strip() for line in (text or '').split('\n') if line.strip()]


def _keys(language: str, lines) -> set:
    return {package_key(language, line) for line in lines or []}


def effective_requirements(env: Environment) -> str:
    """detected + learned + pinned - excluded, as the requirements text the image is built from."""
    by_key: Dict[str, str] = {}
    for line in _lines(env.detected_requirements) + list(env.learned_packages or []):
        by_key.setdefault(package_key(env.language, line), line)
    for line in env.pinned_packages or []:
        by_key[package_key(env.language, line)] = line
    excluded = _keys(env.language, env.excluded_packages)
    return "\n".join(sorted(line for key, line in by_key.items() if key not in excluded))


def refresh_requirements(env: Environment) -> bool:
    """Recompute env.requirements from the lists (no save). True when it changed."""
    if not supports_package_list(env.language):
        return False
    new = effective_requirements(env)
    if new == (env.requirements or ""):
        return False
    env.requirements = new
    return True


def describe_packages(env: Environment) -> List[Dict[str, str]]:
    """The packages in `requirements`, each with where it came from, for the instructor panel."""
    if not supports_package_list(env.language):
        return []
    pinned = _keys(env.language, env.pinned_packages)
    learned = _keys(env.language, env.learned_packages)
    described = []
    for line in _lines(env.requirements):
        key = package_key(env.language, line)
        origin = 'pinned' if key in pinned else 'learned' if key in learned else 'detected'
        described.append({"name": package_name(line), "requirement": line, "origin": origin})
    return described


def pending_packages(env: Environment) -> List[Dict[str, Any]]:
    """Packages student runs needed that are not in `requirements`: still counting, or refused."""
    pending = []
    for name, entry in (env.convergence_stats or {}).items():
        if not isinstance(entry, dict) or entry.get("status") == "learned":
            continue
        pending.append({
            "name": name,
            "count": len(entry.get("submissions") or []),
            "status": entry.get("status") or "counting",
        })
    return sorted(pending, key=lambda p: p["name"])


def image_out_of_date(env: Environment) -> bool:
    """An image exists but was built from different requirements (or from unknown ones)."""
    return bool(env.image_name) and env.built_requirements != (env.requirements or "")


def validate_requirement(language: str, text: str, check_pypi: bool = True) -> str:
    """Normalise what an instructor typed into one requirement line, or raise InvalidPackage."""
    line = re.sub(r'\s+', '', text or '')
    family = language_family(language)
    if family == 'python':
        if not _PYTHON_REQUIREMENT.match(line):
            raise InvalidPackage("Enter a package name, optionally with a version such as numpy==1.26.4.")
        name = package_name(line)
        if check_pypi and not Autodetector.check_pypi_existence(name):
            raise InvalidPackage(f"'{name}' was not found on PyPI. Check the spelling.")
        return line
    if family == 'r':
        if not _R_PACKAGE.match(line):
            raise InvalidPackage("Enter the name of an R package, such as ggplot2.")
        return line
    raise InvalidPackage("Packages can only be added here for Python and R environments.")


def add_package(env: Environment, text: str, check_pypi: bool = True) -> str:
    """Pin a package (no save). It also lifts an exclusion or a failed-install mark on it."""
    line = validate_requirement(env.language, text, check_pypi)
    key = package_key(env.language, line)
    env.pinned_packages = [p for p in env.pinned_packages or [] if package_key(env.language, p) != key] + [line]
    env.excluded_packages = [n for n in env.excluded_packages or [] if package_key(env.language, n) != key]
    env.convergence_stats = {name: entry for name, entry in (env.convergence_stats or {}).items()
                             if package_key(env.language, name) != key}
    refresh_requirements(env)
    return line


def remove_package(env: Environment, name: str) -> None:
    """Exclude a package (no save). The lists keep it, so restoring brings it back as it was."""
    key = package_key(env.language, name)
    if key and key not in _keys(env.language, env.excluded_packages):
        env.excluded_packages = list(env.excluded_packages or []) + [package_name(name)]
    refresh_requirements(env)


def restore_package(env: Environment, name: str) -> None:
    """Lift an exclusion (no save)."""
    key = package_key(env.language, name)
    env.excluded_packages = [n for n in env.excluded_packages or [] if package_key(env.language, n) != key]
    refresh_requirements(env)


def restore_snapshot(env: Environment, requirements: str) -> None:
    """Make `requirements` equal a past build's (no save), in a way that sticks.

    Packages added since are excluded and packages dropped since are pinned, so detection and
    learning cannot undo the rollback. The instructor can lift each exclusion again.
    """
    if not supports_package_list(env.language):
        env.requirements = requirements or ""
        return
    target = {package_key(env.language, line): line for line in _lines(requirements)}
    current = {package_key(env.language, line): line for line in _lines(effective_requirements(env))}
    for key, line in current.items():
        if key not in target:
            env.excluded_packages = list(env.excluded_packages or []) + [package_name(line)]
    for key, line in target.items():
        if current.get(key) != line:
            env.pinned_packages = [p for p in env.pinned_packages or []
                                   if package_key(env.language, p) != key] + [line]
            env.excluded_packages = [n for n in env.excluded_packages or []
                                     if package_key(env.language, n) != key]
    refresh_requirements(env)


def schedule_rebuild(environment_id: int, reason: str, rate_limited: bool = True) -> bool:
    """Queue one automatic rebuild for the environment. False when one is already queued.

    rate_limited (packages learned from runs, or re-detected) keeps builds REBUILD_MIN_INTERVAL
    apart; an instructor's own change only waits out the debounce.
    """
    from autograder.run import RebuildEnvironmentIfStale

    now = timezone.now()
    delay = REBUILD_DEBOUNCE_SECONDS
    if rate_limited:
        last_built = Environment.objects.filter(pk=environment_id).values_list('last_built', flat=True).first()
        if last_built:
            delay = max(delay, int((last_built + REBUILD_MIN_INTERVAL - now).total_seconds()))
    claimed = Environment.objects.filter(pk=environment_id).filter(
        Q(rebuild_scheduled_at__isnull=True) | Q(rebuild_scheduled_at__lt=now - REBUILD_CLAIM_EXPIRY)
    ).update(rebuild_scheduled_at=now + timedelta(seconds=delay))
    if not claimed:
        return False
    try:
        RebuildEnvironmentIfStale.apply_async(args=[environment_id, reason], countdown=delay)
    except Exception:
        # Broker down: give the claim back, or nothing could queue a rebuild until it expires.
        Environment.objects.filter(pk=environment_id).update(rebuild_scheduled_at=None)
        raise
    logger.info(f"[Packages] Rebuild of env {environment_id} queued in {delay}s ({reason})")
    return True


def settle_learned_packages(environment_id: int, build_succeeded: bool) -> List[int]:
    """After a build: close the books on packages learned since the last successful one.

    Success: they are in the image now; returns the submissions that failed for want of them, to
    rerun. Failure, when those packages are the only change since the last good image: they are
    what broke the build, so they are dropped and marked so they are not learned again.
    """
    from django.db import transaction

    with transaction.atomic():
        env = Environment.objects.select_for_update().get(pk=environment_id)
        stats = dict(env.convergence_stats or {})
        unbuilt = [name for name, entry in stats.items()
                   if isinstance(entry, dict) and entry.get("status") == "learned"]
        if not unbuilt:
            return []

        if build_succeeded:
            rerun: List[int] = []
            for name in unbuilt:
                rerun.extend(stats.pop(name).get("rerun") or [])
            env.convergence_stats = stats
            env.save(update_fields=['convergence_stats'])
            return sorted(set(rerun))

        if env.built_requirements is None:
            return []
        changed = _keys(env.language, _lines(env.requirements)) ^ _keys(env.language, _lines(env.built_requirements))
        if not changed or not changed <= _keys(env.language, unbuilt):
            return []
        for name in unbuilt:
            stats[name] = {**stats[name], "status": "build_failed"}
        unbuilt_keys = _keys(env.language, unbuilt)
        env.learned_packages = [p for p in env.learned_packages or []
                                if package_key(env.language, p) not in unbuilt_keys]
        env.convergence_stats = stats
        refresh_requirements(env)
        env.build_logs = (env.build_logs or "") + (
            f"\nRemoved packages learned from student runs that could not be installed: "
            f"{', '.join(sorted(unbuilt))}. The previous image is still in use.\n")
        env.save(update_fields=['learned_packages', 'convergence_stats', 'requirements', 'build_logs'])
        logger.warning(f"[Packages] Env {environment_id}: dropped learned packages {unbuilt} after a failed build")
        return []
