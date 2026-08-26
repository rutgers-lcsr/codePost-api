# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Write-tool guardrails.

Tiers (enforced by tools; scope is enforced by the registry before any of this):

- Tier 0 — reversible, staff-visible only. ``dryRun`` available, defaults False.
- Tier 1 — student-visible but recoverable. ``dryRun`` defaults **True**: the
  first call is always a preview, and re-issuing with ``dryRun=false`` costs the
  model one turn. The preview is the guardrail.
- Tier 2 — irreversible-ish or wide blast radius. Preview first, then the real
  call must carry the ``confirmToken`` the preview returned. The token is an
  HMAC over the *plan*, so it cannot be fabricated by the model, expires in
  5 minutes, and dies if the plan changes between preview and confirm (a TA
  finalizing more submissions mid-flow forces a re-preview).

A plain ``confirm: true`` boolean would be useless at any tier — a model that
sees it in the schema sets it on the first call, every time.

Stateless on purpose: HMAC + TTL works identically across every worker with no
session and no Redis. (Tier 3 — out-of-band human confirmation codes for
deletes/resets/mass email — arrives with those tools.)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta as datetime_timedelta

from django.conf import settings

from core.agent import errors

TOKEN_TTL_SECONDS = 300


def _canonical(tool: str, args: dict, plan_hash: str, course_id: int, user_id: int,
               issued_at: int) -> bytes:
    # confirmToken/dryRun are stripped so the token binds the operation, not
    # the confirmation ceremony around it.
    clean = {k: v for k, v in sorted(args.items())
             if k not in ('confirmToken', 'dryRun')}
    return json.dumps([tool, clean, plan_hash, course_id, user_id, issued_at],
                      sort_keys=True, separators=(',', ':'), default=str).encode()


def plan_hash(plan: dict) -> str:
    """Fingerprint of the computed plan (recipient counts, cascade sizes, …)."""
    raw = json.dumps(plan, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def issue_token(tool: str, args: dict, plan: dict, *, course_id: int,
                user_id: int) -> dict:
    issued_at = int(time.time())
    digest = hmac.new(
        settings.SECRET_KEY.encode(),
        _canonical(tool, args, plan_hash(plan), course_id, user_id, issued_at),
        hashlib.sha256,
    ).hexdigest()[:32]
    return {
        'confirmToken': f'{issued_at}.{digest}',
        'confirmTokenExpiresInSeconds': TOKEN_TTL_SECONDS,
    }


def verify_token(token: str, tool: str, args: dict, plan: dict, *, course_id: int,
                 user_id: int) -> None:
    """Raise a ToolError unless *token* matches this exact plan, fresh."""
    try:
        issued_str, digest = token.split('.', 1)
        issued_at = int(issued_str)
    except (AttributeError, ValueError):
        raise errors.ToolError(
            'CONFIRM_TOKEN_STALE', 'The confirmToken is malformed.',
            remedy='Re-run with dryRun=true to get a fresh preview and token.',
            retryable=True)

    if time.time() - issued_at > TOKEN_TTL_SECONDS:
        raise errors.ToolError(
            'CONFIRM_TOKEN_STALE', 'The confirmToken has expired.',
            remedy='Re-run with dryRun=true to get a fresh preview and token.',
            retryable=True)

    expected = hmac.new(
        settings.SECRET_KEY.encode(),
        _canonical(tool, args, plan_hash(plan), course_id, user_id, issued_at),
        hashlib.sha256,
    ).hexdigest()[:32]
    if not hmac.compare_digest(digest, expected):
        raise errors.ToolError(
            'CONFIRM_TOKEN_STALE',
            'The plan changed since the preview (or the token does not match '
            'this operation).',
            remedy='Re-run with dryRun=true, review the new preview, and confirm '
                   'with the fresh token.',
            retryable=True)


def confirmation_required(tool: str, args: dict, plan: dict, *, course_id: int,
                          user_id: int, message: str) -> errors.ToolError:
    """The error a Tier-2 tool returns from its preview: the plan plus a token.

    Returned inline so the confirm retry is one turn, not two.
    """
    token = issue_token(tool, args, plan, course_id=course_id, user_id=user_id)
    return errors.ToolError(
        'CONFIRMATION_REQUIRED', message,
        remedy='Review the plan with the user, then re-call with dryRun=false '
               'and this confirmToken.',
        retryable=True,
        context={'plan': plan, **token})


# ---------------------------------------------------------------------------
# Tier 3 — out-of-band human confirmation codes
# ---------------------------------------------------------------------------
# The HMAC tokens above are a race guard, not a human gate: the server issues
# them and the agent consumes them, so an agent can do preview→confirm alone.
# Tier-3 operations (unrecoverable destruction, mass email) instead mint a
# short code delivered ONLY through the course dashboard — a channel the agent
# cannot read (the panel endpoint rejects course-scoped credentials) — so a
# human must fetch it and paste it into the chat.

import secrets

CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'   # no 0/O/1/I/L lookalikes


def _args_hash(tool: str, args: dict) -> str:
    clean = {k: v for k, v in sorted(args.items())
             if k not in ('confirmationCode', 'confirmToken', 'dryRun')}
    raw = json.dumps([tool, clean], sort_keys=True, separators=(',', ':'),
                     default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _generate_code() -> str:
    body = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    return f'{body[:3]}-{body[3:]}'


def require_confirmation_code(tool: str, args: dict, plan: dict, *, ctx,
                              message: str) -> errors.ToolError:
    """Mint a dashboard code for this exact operation and refuse the call.

    Re-previewing an identical, still-active request reuses its code rather
    than littering the dashboard with duplicates.
    """
    from django.utils import timezone

    from core.models import PendingAgentAction

    ah, ph = _args_hash(tool, args), plan_hash(plan)
    now = timezone.now()

    action = PendingAgentAction.objects.filter(
        course=ctx.course, tool=tool, args_hash=ah, plan_hash=ph,
        redeemed_at=None, expires_at__gt=now).first()
    if action is None:
        action = PendingAgentAction.objects.create(
            course=ctx.course, tool=tool, args_hash=ah, plan_hash=ph,
            plan=plan, code=_generate_code(),
            requested_by=ctx.user if getattr(ctx.user, 'pk', None) else None,
            expires_at=now + datetime_timedelta(
                minutes=PendingAgentAction.EXPIRY_MINUTES))

    return errors.ToolError(
        'CONFIRMATION_REQUIRED', message,
        remedy=('A confirmation code was posted to the codePost dashboard '
                '(Course Settings → Pending agent actions). Ask the user to '
                'open it, read the code, and paste it here; then re-call with '
                'confirmationCode set. It expires in '
                f'{PendingAgentAction.EXPIRY_MINUTES} minutes and works once.'),
        retryable=True,
        context={'plan': plan,
                 'expiresAt': action.expires_at.isoformat()})


def verify_confirmation_code(code: str, tool: str, args: dict, plan: dict, *,
                             ctx) -> None:
    """Redeem a dashboard code; raise unless it matches this exact operation."""
    from django.utils import timezone

    from core.models import PendingAgentAction

    normalized = (code or '').strip().upper().replace(' ', '')
    if '-' not in normalized and len(normalized) == 6:
        normalized = f'{normalized[:3]}-{normalized[3:]}'
    if not normalized:
        raise errors.ToolError(
            'CONFIRMATION_CODE_INVALID',
            'This operation needs the confirmation code from the dashboard.',
            remedy='Ask the user for the code shown under Course Settings → '
                   'Pending agent actions, then re-call with confirmationCode.',
            retryable=True)

    now = timezone.now()
    action = PendingAgentAction.objects.filter(
        course=ctx.course, tool=tool, code=normalized).order_by('-created').first()

    if action is None or action.redeemed_at is not None or action.expires_at <= now:
        raise errors.ToolError(
            'CONFIRMATION_CODE_INVALID',
            'That code is unknown, already used, or expired.',
            remedy='Re-run the tool without a code to mint a fresh one, and ask '
                   'the user to read it from the dashboard again.',
            retryable=True)

    if action.args_hash != _args_hash(tool, args) or \
            action.plan_hash != plan_hash(plan):
        raise errors.ToolError(
            'CONFIRMATION_CODE_INVALID',
            'The operation (or its blast radius) changed since the code was '
            'issued — the code no longer applies.',
            remedy='Re-run without a code to get a fresh preview and code for '
                   'the current state.', retryable=True)

    action.redeemed_at = now
    action.save(update_fields=['redeemed_at', 'modified'])
