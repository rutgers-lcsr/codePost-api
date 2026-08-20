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
