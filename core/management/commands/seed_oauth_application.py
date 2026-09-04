# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Seed the fallback OAuth Application for Claude connectors.

Dynamic client registration is the primary path (Claude auto-registers), but
the connector UI's optional "OAuth Client ID" field needs a pre-registered
client to point at when auto-registration is unavailable. Idempotent — safe in
init.sh / deploys.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the pre-registered public OAuth client for Claude."

    def handle(self, *args, **options):
        from oauth2_provider.models import Application

        app, created = Application.objects.update_or_create(
            name="Claude (fallback)",
            defaults={
                "client_type": Application.CLIENT_PUBLIC,
                "authorization_grant_type": Application.GRANT_AUTHORIZATION_CODE,
                "skip_authorization": False,
                "client_secret": "",
                # http://localhost/callback matches any port via the RFC 8252
                # loopback exemption (ALLOW_LOCALHOST_LOOPBACK) — Claude Code
                # picks a random one.
                "redirect_uris": (
                    "https://claude.ai/api/mcp/auth_callback "
                    "https://claude.com/api/mcp/auth_callback "
                    "http://localhost/callback"
                ),
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(f"{verb} fallback OAuth application.")
        self.stdout.write(f"client_id: {app.client_id}")
