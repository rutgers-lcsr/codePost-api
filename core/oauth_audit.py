# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Audit receivers for the OAuth authorization server.

Consent is course-agnostic, so CourseAuditEvent (course FK required) doesn't
fit — these land in the generic log.Event table instead. Wired up in
core/apps.py:ready().
"""
from __future__ import annotations

import json

from django.db.models.signals import post_save
from django.dispatch import receiver


def register_oauth_audit_receivers() -> None:
    from oauth2_provider.models import Application, Grant

    @receiver(post_save, sender=Grant, weak=False,
              dispatch_uid="oauth_audit_grant")
    def on_consent_granted(sender, instance, created, **kwargs):
        if not created:
            return
        _log("oauth_consent_granted",
             user=getattr(instance.user, "email", None),
             meta={"application": instance.application.name,
                   "clientId": instance.application.client_id,
                   "scopes": instance.scope})

    @receiver(post_save, sender=Application, weak=False,
              dispatch_uid="oauth_audit_dcr")
    def on_client_registered(sender, instance, created, **kwargs):
        # DCR-created applications have no owning user; admin/seeded ones may.
        if not created or instance.user_id is not None:
            return
        _log("oauth_dcr_registered",
             user=None,
             meta={"clientName": instance.name,
                   "clientId": instance.client_id,
                   "redirectUris": instance.redirect_uris})


def _log(description: str, *, user, meta: dict) -> None:
    try:
        from log.models import Event
        Event.objects.create(category="oauth", type="audit",
                             description=description, user=user,
                             meta=json.dumps(meta, default=str))
    except Exception:                                          # pragma: no cover
        # Auditing must never break the auth flow itself.
        pass
