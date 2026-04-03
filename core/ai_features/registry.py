# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
AI Feature Registry — single source of truth for toggleable AI features.

Register a new AI feature by creating a file in ``core/ai_features/`` and
calling ``register_ai_feature()``.  The registry is consumed by:

* ``AIService.is_feature_enabled()`` — endpoint guards
* ``GET /aiFeatures/`` API endpoint — so settings UIs discover features dynamically
* Course / Organization ``aiFeatureConfig`` JSONField — stores per-feature overrides
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AIFeatureEntry:
    """A registered AI feature."""
    key: str
    label: str
    description: str
    default_enabled: bool
    requires: tuple[str, ...]


class AIFeatureRegistry:
    """Global registry of AI features and their defaults."""

    def __init__(self) -> None:
        self._entries: dict[str, AIFeatureEntry] = {}

    def register(
        self,
        key: str,
        *,
        label: str,
        description: str = '',
        default_enabled: bool = True,
        requires: list[str] | None = None,
    ) -> None:
        if key in self._entries:
            raise ValueError(f"AI feature '{key}' is already registered.")
        self._entries[key] = AIFeatureEntry(
            key=key,
            label=label,
            description=description,
            default_enabled=default_enabled,
            requires=tuple(requires or []),
        )

    def get(self, key: str) -> AIFeatureEntry | None:
        return self._entries.get(key)

    def get_default(self, key: str) -> bool:
        entry = self._entries.get(key)
        return entry.default_enabled if entry else True

    def all(self) -> list[AIFeatureEntry]:
        return list(self._entries.values())

    def keys(self) -> list[str]:
        return list(self._entries.keys())

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def dependents_of(self, key: str) -> list[str]:
        """Return keys of features that require *key*."""
        return [e.key for e in self._entries.values() if key in e.requires]


# Module-level singleton
ai_feature_registry = AIFeatureRegistry()


def register_ai_feature(
    key: str,
    *,
    label: str,
    description: str = '',
    default_enabled: bool = True,
    requires: list[str] | None = None,
):
    """Decorator that registers an AI feature at import time.

    Usage::

        @register_ai_feature('comment_generation', label='Comment Generation', ...)
        def _feature():
            pass
    """
    def decorator(fn):
        ai_feature_registry.register(
            key,
            label=label,
            description=description,
            default_enabled=default_enabled,
            requires=requires,
        )
        return fn
    return decorator
