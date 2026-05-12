# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Prompt Registry — single source of truth for all AI prompt types.

Register a new prompt type by creating a file in ``core/prompts/`` and
calling ``register_prompt()``.  The registry is consumed by:

* ``SystemPromptVariant.PROMPT_TYPE_CHOICES``
* ``AIService.resolve_prompt()`` (for fallback text when no DB variant exists)
* ``/promptTypes/`` API endpoint (so the Prompt Lab UI discovers types dynamically)
* ``manage.py seed_prompts`` (auto-creates an active DB variant per registered type)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PromptTypeEntry:
    """A registered prompt type."""
    key: str
    label: str
    description: str
    default_template: str
    allowed_placeholders: frozenset[str] = frozenset()


class PromptRegistry:
    """Global registry of prompt types and their default templates."""

    def __init__(self) -> None:
        self._entries: dict[str, PromptTypeEntry] = {}

    def register(
        self,
        key: str,
        *,
        label: str,
        description: str = '',
        default_template: str = '',
        allowed_placeholders: frozenset[str] | None = None,
    ) -> None:
        """Register a prompt type. Raises ``ValueError`` on duplicate keys."""
        if key in self._entries:
            raise ValueError(f"Prompt type '{key}' is already registered.")
        self._entries[key] = PromptTypeEntry(
            key=key,
            label=label,
            description=description,
            default_template=default_template,
            allowed_placeholders=allowed_placeholders or frozenset(),
        )

    def choices(self) -> list[tuple[str, str]]:
        """Return a Django-style choices list for model fields."""
        return [(e.key, e.label) for e in self._entries.values()]

    def get(self, key: str) -> PromptTypeEntry | None:
        return self._entries.get(key)

    def get_default_template(self, key: str) -> str:
        entry = self._entries.get(key)
        return entry.default_template if entry else ''

    def get_allowed_placeholders(self, key: str) -> frozenset[str]:
        entry = self._entries.get(key)
        return entry.allowed_placeholders if entry else frozenset()

    def all(self) -> list[PromptTypeEntry]:
        return list(self._entries.values())

    def keys(self) -> list[str]:
        return list(self._entries.keys())

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def __len__(self) -> int:
        return len(self._entries)


# Module-level singleton
prompt_registry = PromptRegistry()


def register_prompt(
    key: str,
    *,
    label: str,
    description: str = '',
    allowed_placeholders: frozenset[str] | None = None,
) -> Callable[[str], str]:
    """Decorator that registers a prompt type and returns the template string unchanged.

    Usage::

        from core.prompts.registry import register_prompt

        @register_prompt('my_feature', label='My Feature', description='Does stuff')
        def DEFAULT_TEMPLATE():
            return '''You are an AI assistant...'''

    Or without the decorator, just call ``prompt_registry.register(...)`` directly.
    """
    def decorator(func: Callable[[], str]) -> str:
        template = func()
        prompt_registry.register(
            key,
            label=label,
            description=description,
            default_template=template,
            allowed_placeholders=allowed_placeholders,
        )
        return template
    return decorator  # type: ignore[return-value]
