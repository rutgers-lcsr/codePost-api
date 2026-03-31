# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Main File Detection

Heuristic-based detection of the primary student file in a submission.
Used by the auto-generation flow to focus AI-generated comments and summaries
on the most important file. Falls back to None when ambiguous, which triggers
the existing all-files generation behavior.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Submission, SubmissionFile

logger = logging.getLogger(__name__)

# Language-specific entry point patterns (compiled once)
_ENTRY_POINT_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    'python': [
        re.compile(r'''if\s+__name__\s*==\s*['"]__main__['"]\s*:'''),
    ],
    'java': [
        re.compile(r'public\s+static\s+void\s+main\s*\('),
    ],
    'c': [
        re.compile(r'\bint\s+main\s*\('),
    ],
    'node': [
        # Common Node entry points don't have a canonical marker,
        # but we match common patterns
        re.compile(r'''require\s*\(\s*['"]express['"]\s*\)|app\.listen\s*\('''),
    ],
}

# Map Environment.language prefixes to pattern keys
_LANGUAGE_PREFIX_MAP: dict[str, str] = {
    'python': 'python',
    'java': 'java',
    'c/c++': 'c',
    'node': 'node',
}

# Well-known "main file" names per language (without extension)
_MAIN_FILE_NAMES: dict[str, set[str]] = {
    'python': {'main', '__main__'},
    'java': {'main', 'app', 'application'},
    'c': {'main'},
    'node': {'index', 'app', 'main', 'server'},
    'r': {'main', 'analysis'},
    'ruby': {'main', 'app'},
    'php': {'index', 'main', 'app'},
}

# Score weights
_SCORE_REQUIRED_FILE = 3
_SCORE_TEST_TARGET = 3
_SCORE_ENTRY_POINT_CODE = 4
_SCORE_MAIN_FILENAME = 3
_SCORE_ASSIGNMENT_NAME_MATCH = 4
_SCORE_DESCRIPTION_MENTION = 2
_SCORE_LARGEST_FILE = 1

# Minimum score for confident detection
_CONFIDENCE_THRESHOLD = 3


def detect_main_file(submission: Submission) -> SubmissionFile | None:
    """Detect the primary student file in a submission.

    Uses a scoring heuristic that considers:
    - Whether there's only one student file (instant pick)
    - Assignment name matching the filename
    - Whether the file is required by the assignment
    - Whether test categories target the file
    - Language-specific entry point patterns in the code
    - Well-known main file names
    - Assignment description mentions
    - File size as a tiebreaker

    Returns the detected SubmissionFile, or None if no file exceeds the
    confidence threshold (signals the caller to fall back to all-files behavior).
    """
    from core.models import SubmissionFile as SubmissionFileModel

    assignment = submission.assignment

    # Gather assignment file metadata
    assignment_files = {
        af.name: af
        for af in assignment.files.filter(hidden=False, is_test_resource=False)
    }
    hidden_file_names = set(
        assignment.files.filter(hidden=True).values_list('name', flat=True)
    )

    # Get all submission files
    submission_files = list(SubmissionFileModel.objects.filter(submission=submission))

    # Filter to student files only (non-hidden, non-test-resource)
    student_files = [
        sf for sf in submission_files
        if sf.name in assignment_files or sf.name not in hidden_file_names
    ]

    if not student_files:
        logger.debug(f"[MainFileDetection] No student files found for submission {submission.id}")
        return None

    # Trivial case: only one student file
    if len(student_files) == 1:
        logger.info(f"[MainFileDetection] Single student file '{student_files[0].name}' for submission {submission.id}")
        return student_files[0]

    # Determine language from Environment (if available)
    language_key = _get_language_key(assignment)

    # Collect scoring signals
    required_names = {
        name for name, af in assignment_files.items() if af.required
    }
    test_target_names = set(
        assignment.testCategories.exclude(targetFileName__isnull=True)
        .exclude(targetFileName='')
        .values_list('targetFileName', flat=True)
    )

    ai_description = getattr(assignment, 'ai_description', '') or ''
    assignment_name_lower = assignment.name.lower().strip()

    # Score each student file
    scores: dict[int, int] = {}
    reasons: dict[int, list[str]] = {}

    for sf in student_files:
        score = 0
        file_reasons: list[str] = []
        file_stem = _file_stem(sf.name)

        # Signal: required assignment file
        if sf.name in required_names:
            score += _SCORE_REQUIRED_FILE
            file_reasons.append('required')

        # Signal: test category targets this file
        if sf.name in test_target_names:
            score += _SCORE_TEST_TARGET
            file_reasons.append('test-target')

        # Signal: filename matches assignment name
        if _names_match(file_stem, assignment_name_lower):
            score += _SCORE_ASSIGNMENT_NAME_MATCH
            file_reasons.append('assignment-name-match')

        # Signal: well-known main filename for the language
        if language_key and file_stem.lower() in _MAIN_FILE_NAMES.get(language_key, set()):
            score += _SCORE_MAIN_FILENAME
            file_reasons.append(f'main-filename({language_key})')

        # Signal: entry point pattern in code
        if language_key and _has_entry_point(sf, language_key):
            score += _SCORE_ENTRY_POINT_CODE
            file_reasons.append(f'entry-point({language_key})')

        # Signal: AI description mentions this filename
        if ai_description and sf.name.lower() in ai_description.lower():
            score += _SCORE_DESCRIPTION_MENTION
            file_reasons.append('description-mention')

        scores[sf.id] = score
        reasons[sf.id] = file_reasons

    # Tiebreaker: largest file gets +1
    if student_files:
        largest = max(student_files, key=lambda sf: len(sf.data or ''))
        scores[largest.id] = scores.get(largest.id, 0) + _SCORE_LARGEST_FILE
        reasons.setdefault(largest.id, []).append('largest-file')

    # Pick the winner
    best_file = max(student_files, key=lambda sf: scores.get(sf.id, 0))
    best_score = scores.get(best_file.id, 0)

    logger.info(
        f"[MainFileDetection] Submission {submission.id} scores: "
        + ", ".join(
            f"{sf.name}={scores.get(sf.id, 0)} ({', '.join(reasons.get(sf.id, []))})"
            for sf in student_files
        )
    )

    if best_score < _CONFIDENCE_THRESHOLD:
        logger.info(
            f"[MainFileDetection] No confident main file for submission {submission.id} "
            f"(best: {best_file.name}={best_score}, threshold={_CONFIDENCE_THRESHOLD})"
        )
        return None

    logger.info(
        f"[MainFileDetection] Detected main file '{best_file.name}' "
        f"(score={best_score}) for submission {submission.id}"
    )
    return best_file


def _get_language_key(assignment) -> str | None:
    """Extract a normalized language key from the assignment's Environment."""
    try:
        env = assignment.environment
    except Exception:
        return None

    lang = (env.language or '').lower()
    for prefix, key in _LANGUAGE_PREFIX_MAP.items():
        if lang.startswith(prefix):
            return key
    return None


def _file_stem(filename: str) -> str:
    """Return filename without its last extension: 'main.py' -> 'main'."""
    dot = filename.rfind('.')
    return filename[:dot] if dot > 0 else filename


def _names_match(file_stem: str, assignment_name: str) -> bool:
    """Check if a file stem plausibly matches the assignment name.

    Handles common transformations: case folding, underscores/hyphens → spaces,
    and substring matching for multi-word assignment names.
    """
    stem = file_stem.lower().replace('_', ' ').replace('-', ' ')
    name = assignment_name.lower().replace('_', ' ').replace('-', ' ')
    if not stem or not name:
        return False
    # Exact match after normalization
    if stem == name:
        return True
    # Stem is a significant substring of the assignment name or vice versa
    if len(stem) >= 3 and (stem in name or name in stem):
        return True
    return False


def _has_entry_point(sf, language_key: str) -> bool:
    """Check if a submission file contains a language-specific entry point pattern."""
    patterns = _ENTRY_POINT_PATTERNS.get(language_key, [])
    if not patterns:
        return False
    content = sf.data or ''
    # Only scan the first 100KB to avoid expensive regex on huge files
    content = content[:100_000]
    return any(p.search(content) for p in patterns)
