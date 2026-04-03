# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Core logic for auto-improving system prompts based on user feedback.

Used by:
- The manual ``auto-improve`` API action
- The scheduled Celery task
- The feedback-threshold signal trigger
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.models import PromptFeedback, SystemPromptVariant

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


def auto_improve_prompt(
    prompt_type: str,
    *,
    min_feedback: int = 5,
    triggered_by: str = 'manual',
    user: User | None = None,
) -> SystemPromptVariant | None:
    """Gather feedback, call AI, and create an improved draft variant.

    Returns the new ``SystemPromptVariant`` on success, or ``None`` if there
    isn't enough feedback.

    Args:
        prompt_type: One of ``SystemPromptVariant.PROMPT_TYPE_CHOICES``.
        min_feedback: Minimum feedback count required to proceed.
        triggered_by: Label stored in metadata (``'manual'``, ``'schedule'``,
            ``'threshold'``).
        user: Optional staff user to set as ``created_by``.
    """
    feedback_qs = PromptFeedback.objects.filter(
        prompt_type=prompt_type,
        is_custom_context=False,
    ).order_by('-created')[:100]

    feedback_list = list(feedback_qs.values(
        'rating', 'feedback_text', 'ai_output_a', 'ai_output_b',
    ))

    if len(feedback_list) < min_feedback:
        logger.info(
            f"[AutoImprove] Not enough feedback for {prompt_type}: "
            f"{len(feedback_list)}/{min_feedback}"
        )
        return None

    active_variant = SystemPromptVariant.objects.filter(
        prompt_type=prompt_type, status='active',
    ).first()

    current_prompt = active_variant.text if active_variant else ''

    thumbs_up = sum(1 for f in feedback_list if f['rating'] == 1)
    thumbs_down = sum(1 for f in feedback_list if f['rating'] == -1)

    text_feedback = [
        f['feedback_text'] for f in feedback_list
        if f['feedback_text'] and f['feedback_text'].strip()
    ]

    neg_outputs = [
        f['ai_output_a'] for f in feedback_list
        if f['rating'] == -1 and f['ai_output_a']
    ][:10]

    pos_outputs = [
        f['ai_output_a'] for f in feedback_list
        if f['rating'] == 1 and f['ai_output_a']
    ][:5]

    meta_prompt = _build_improvement_prompt(
        prompt_type=prompt_type,
        current_prompt=current_prompt,
        thumbs_up=thumbs_up,
        thumbs_down=thumbs_down,
        text_feedback=text_feedback,
        neg_outputs=neg_outputs,
        pos_outputs=pos_outputs,
    )

    improved_text = _call_ai_for_improvement(meta_prompt)

    parent_version = active_variant.version if active_variant else 0
    new_variant = SystemPromptVariant.objects.create(
        prompt_type=prompt_type,
        name=f"Auto-improved {prompt_type.replace('_', ' ').title()} v{parent_version + 1}",
        text=improved_text,
        status='draft',
        version=parent_version + 1,
        parent=active_variant,
        created_by=user,
        metadata={
            'auto_generated': True,
            'triggered_by': triggered_by,
            'feedback_count': len(feedback_list),
            'thumbs_up': thumbs_up,
            'thumbs_down': thumbs_down,
            'text_feedback_count': len(text_feedback),
            'parent_variant_id': active_variant.id if active_variant else None,
        },
    )

    logger.info(
        f"[AutoImprove] Created variant {new_variant.id} for {prompt_type} "
        f"(trigger={triggered_by}, feedback={len(feedback_list)}, "
        f"+{thumbs_up}/-{thumbs_down})"
    )
    return new_variant


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_improvement_prompt(
    prompt_type: str,
    current_prompt: str,
    thumbs_up: int,
    thumbs_down: int,
    text_feedback: list[str],
    neg_outputs: list[str],
    pos_outputs: list[str],
) -> str:
    feedback_section = ""
    if text_feedback:
        items = "\n".join(f"  - {t[:300]}" for t in text_feedback[:20])
        feedback_section = f"\n\nUser feedback comments:\n{items}"

    neg_section = ""
    if neg_outputs:
        items = "\n---\n".join(o[:500] for o in neg_outputs[:5])
        neg_section = (
            f"\n\nExamples of AI outputs that received NEGATIVE feedback:\n{items}"
        )

    pos_section = ""
    if pos_outputs:
        items = "\n---\n".join(o[:500] for o in pos_outputs[:3])
        pos_section = (
            f"\n\nExamples of AI outputs that received POSITIVE feedback:\n{items}"
        )

    return f"""You are an expert prompt engineer. Your task is to improve an AI system prompt based on user feedback data.

The prompt is used for: {prompt_type.replace('_', ' ')}

Current system prompt:
\"\"\"
{current_prompt}
\"\"\"

Feedback summary:
- Thumbs up: {thumbs_up}
- Thumbs down: {thumbs_down}
- Approval rate: {(thumbs_up / max(thumbs_up + thumbs_down, 1) * 100):.0f}%{feedback_section}{neg_section}{pos_section}

Instructions:
1. Analyze the feedback patterns — what do users like and dislike about the AI outputs?
2. Identify specific weaknesses in the current prompt that lead to negative feedback.
3. Write an improved version of the system prompt that addresses these issues.
4. Keep the same general structure and placeholder variables (e.g. {{assignment_name}}, {{file_name}}, {{file_content}}).
5. The improved prompt should be concise and actionable.

Output ONLY the improved system prompt text, with no preamble or explanation."""


def _call_ai_for_improvement(meta_prompt: str) -> str:
    """Call AI to generate an improved prompt using PromptLabSettings config."""
    from core.models import PromptLabSettings

    lab = PromptLabSettings.load()
    provider = lab.ai_provider
    api_key = lab.ai_api_key
    model = lab.ai_model

    if not provider or not api_key:
        raise RuntimeError(
            "No AI provider configured for auto-improvement. "
            "Set a provider and API key in the Prompt Lab settings."
        )

    if provider == 'gemini':
        return _call_gemini(api_key, model or 'gemini-2.5-pro', meta_prompt)
    elif provider == 'openai':
        return _call_openai(api_key, model or 'gpt-4o', meta_prompt)
    else:
        raise RuntimeError(f"Unsupported auto-improvement provider: {provider}")


def _call_gemini(api_key: str, model: str, meta_prompt: str) -> str:
    import google.genai as genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=meta_prompt,
        config=types.GenerateContentConfig(
            system_instruction="You are an expert prompt engineer.",
        ),
    )
    text = response.text or ''
    if not text.strip():
        raise RuntimeError("Gemini returned an empty response.")
    return text.strip()


def _call_openai(api_key: str, model: str, meta_prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are an expert prompt engineer."},
            {"role": "user", "content": meta_prompt},
        ],
    )
    text = response.choices[0].message.content or ''
    if not text.strip():
        raise RuntimeError("OpenAI returned an empty response.")
    return text.strip()
