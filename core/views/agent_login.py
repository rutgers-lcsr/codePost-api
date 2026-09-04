# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The browser login bridge for the OAuth consent page.

django-oauth-toolkit's authorize view needs ``request.user`` via a Django
session, and no codePost flow ever creates one — the SPA is JWT-only and the
CAS callback historically redirected straight back to it. This page fills the
gap for exactly one purpose: getting an instructor signed in on the API origin
long enough to approve an agent connection.

Email-first: SSO organizations get their provider button (the CAS callback
completes the session when the validated ``next`` parameter is present — see
core/views/sso.py); password organizations get a password field. SSO-provisioned
users have no usable password (core/utils.py creates them without one), so they
are steered to SSO rather than into a password-error loop.

A plain Django view on purpose — DRF would drag in SessionAuthentication/CSRF
edge cases and schema generation for a page that is pure server-rendered HTML.
"""
from __future__ import annotations

from django.contrib.auth import authenticate, login as auth_login
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from core.throttles import rate_limited

# Consent sessions are single-purpose; don't leave a two-week cookie behind.
SESSION_LIFETIME_SECONDS = 900


def validate_next(raw: str | None) -> str | None:
    """Only a local /o/authorize URL may ride the login flow.

    ``url_has_allowed_host_and_scheme`` with no allowed hosts accepts only
    relative URLs (killing ``https://evil`` and ``//evil``); the prefix check
    stops the login bridge being used to session-bounce anywhere else.
    """
    if not raw:
        return None
    if not url_has_allowed_host_and_scheme(raw, allowed_hosts=None):
        return None
    if not raw.startswith('/o/authorize'):
        return None
    return raw


@never_cache
@rate_limited('agent_login', '10/min')
def agent_login(request):
    next_url = validate_next(request.GET.get('next') or request.POST.get('next'))
    context = {'next': next_url or '', 'error': '', 'email': '', 'mode': 'email'}

    if request.method != 'POST':
        return render(request, 'agent_login.html', context)

    email = (request.POST.get('email') or '').strip().lower()
    password = request.POST.get('password') or ''
    context['email'] = email

    if not email:
        context['error'] = 'Enter your email address.'
        return render(request, 'agent_login.html', context)

    sso = _sso_for_email(email)
    if sso is not None:
        provider, org_id = sso
        if next_url:
            from urllib.parse import quote
            context.update({'mode': 'sso', 'provider': provider,
                            'sso_url': f'/auth/sso/login/{provider}/'
                                       f'?org={org_id}&next={quote(next_url, safe="")}'})
            return render(request, 'agent_login.html', context)
        context['error'] = 'This login page is only used to approve agent connections.'
        return render(request, 'agent_login.html', context)

    if not password:
        context['mode'] = 'password'
        return render(request, 'agent_login.html', context)

    # Usernames are emails by convention (core/utils.py), but resolve via the
    # email column so legacy rows with a different username still work.
    from django.contrib.auth.models import User
    account = User.objects.filter(email__iexact=email).first()
    user = authenticate(request, username=account.username if account else email,
                        password=password)
    if user is None:
        context['mode'] = 'password'
        context['error'] = 'Incorrect email or password.'
        return render(request, 'agent_login.html', context)

    auth_login(request, user)
    request.session.set_expiry(SESSION_LIFETIME_SECONDS)
    return HttpResponseRedirect(next_url or '/')


def _sso_for_email(email: str):
    """(provider, org_id) when the email's organization uses SSO, else None.

    Same resolution check_sso_availability uses (including the
    allowed_email_domains fallback for subdomains).
    """
    from core.views.sso import get_organization_by_email_domain

    domain = email.rsplit('@', 1)[-1]
    org = get_organization_by_email_domain(domain, sso_enabled=True)
    if org and org.sso_provider:
        return org.sso_provider, org.id
    return None
