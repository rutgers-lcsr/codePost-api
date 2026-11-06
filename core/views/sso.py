# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.http import HttpResponseRedirect, JsonResponse
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse
from core.serializers.sso import CheckSSOAvailabilityResponseSerializer, MainOrgSSOConfigSerializer, OrgSSOConfigSerializer
from core.throttles import SSORateThrottle
from django.conf import settings
from django.core.cache import cache
from core.models import Organization, User
from core.utils import get_or_create_user
import requests
import secrets
import json
import urllib.parse
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)

OAUTH_PROVIDERS = ('AZURE', 'GOOGLE', 'OIDC')


def get_organization_by_email_domain(domain, **filters):
    """
    Look up an Organization by email domain. First checks the primary email_domain field,
    then falls back to checking allowed_email_domains (JSONField list) for additional
    domains like subdomains (e.g. scarletmail.rutgers.edu -> rutgers.edu org).
    
    Uses Python-level filtering for allowed_email_domains to maintain SQLite compatibility.
    """
    # 1. Try exact match on primary email_domain
    org = Organization.objects.filter(email_domain=domain, **filters).first()
    if org:
        return org
    
    # 2. Fall back to checking allowed_email_domains (Python-level for SQLite compat)
    for org in Organization.objects.filter(**filters):
        allowed_domains = org.allowed_email_domains or []
        if isinstance(allowed_domains, list) and domain in allowed_domains:
            return org
    
    return None


def _organization_of_unique_user(email):
    """Organization of the one user with this email, else None (none, or ambiguous:
    User.email is not unique and a login must not guess between accounts)."""
    users = list(User.objects.filter(email=email)[:2])
    if len(users) != 1:
        return None
    return users[0].profile.organization


def _issue_browser_state(request):
    """A fresh login state, remembered in this browser's session (login CSRF:
    the callback only honours a state that its own browser started)."""
    state = secrets.token_urlsafe(32)
    request.session[f"sso_state:{state}"] = True
    return state


def _browser_state_error(request, state):
    """Why `state` is refused, or None after claiming it (single use)."""
    if not state:
        return 'Missing state parameter'
    if not request.session.pop(f"sso_state:{state}", False):
        return 'State parameter was not issued to this browser'
    return None


# Helper to get service URL
def get_service_url(request, provider, org_id=None, next_path=None, state=None):
    # Construct the callback URL dynamically based on the request's host
    # e.g. https://api.codepost.io/auth/sso/callback/CAS/?org=123
    host = request.get_host()
    scheme = request.scheme
    # Ensure usage of https in production if behind proxy
    if settings.DEBUG is False:
        scheme = 'https'
    
    url = f"{scheme}://{host}/auth/sso/callback/{provider}/"
    if org_id:
        url += f"?org={org_id}"
    if next_path:
        # OAuth consent flow (see core/views/agent_login.py): the local
        # /o/authorize URL rides the CAS service URL so the callback can finish
        # with a session instead of a SPA JWT redirect. CAS requires the login
        # and validation legs to use a byte-identical service URL — both call
        # sites build it here, threading the raw incoming value.
        url += f"&next={urllib.parse.quote(next_path, safe='')}"
    if state:
        # CAS's only binding between a ticket and a browser: the ticket is
        # valid for this exact URL, and the state in it lives in one session.
        url += f"&state={state}"
    return url

def sso_gate_error(organization, provider):
    """Return (message, http_status) if this org may not use SSO via `provider`, else None.

    Shared by initiate_sso and sso_callback so both apply the same gates.
    """
    if not organization.sso_enabled:
        return 'SSO is not enabled for this organization', 403
    if organization.sso_provider != provider:
        return f'Organization is configured for {organization.sso_provider}, not {provider}', 400
    return None


def _json_error(message, status):
    return JsonResponse(dict(error=message), status=status)


def _initiate_organization(request):
    """The organization an SSO login is for, from `org` or `email`: (organization, None),
    or (None, error response)."""
    org_id = request.query_params.get('org')
    if org_id:
        try:
            return Organization.objects.get(id=org_id), None
        except (Organization.DoesNotExist, ValueError, TypeError):
            return None, _json_error('Organization not found', 404)
    email = request.query_params.get('email')
    organization = _organization_of_email(email) if email else None
    if not organization:
        return None, _json_error('Could not determine organization for SSO', 400)
    return organization, None


def _organization_of_email(email):
    domain = email.split('@')[-1]
    return get_organization_by_email_domain(domain) or _organization_of_unique_user(email)


def _azure_endpoint(sso_config, leaf):
    tenant = sso_config.get('tenant_id', 'common')
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/{leaf}"


def _initiate_cas(request, organization, sso_config):
    cas_url = sso_config.get('cas_server_url')
    if not cas_url:
        return _json_error('CAS Server URL is missing from config', 500)

    # Pass org_id to service URL so we can retrieve config on callback.
    # A validated `next` (OAuth consent flow) rides along too.
    from core.views.agent_login import validate_next
    next_path = validate_next(request.query_params.get('next'))
    service_url = get_service_url(request, 'CAS', organization.id, next_path,
                                  _issue_browser_state(request))
    encoded_service = urllib.parse.quote(service_url)

    # USE PROVIDED URL AS LOGIN ENDPOINT DIRECTLY (per user request)
    separator = '&' if '?' in cas_url else '?'
    return HttpResponseRedirect(f"{cas_url}{separator}service={encoded_service}")


def _oidc_authorization_endpoint(sso_config):
    """(authorization endpoint, None), or (None, error response)."""
    discovery = sso_config.get('discovery_url')
    if not discovery:
        return None, _json_error('Discovery URL missing', 500)
    try:
        resp = requests.get(discovery, timeout=5).json()
        return resp.get('authorization_endpoint'), None
    except Exception as e:
        return None, _json_error(f'Failed to fetch OIDC config: {e}', 500)


def _authorization_endpoint(provider, sso_config):
    """(authorization endpoint, None), or (None, error response)."""
    if provider == 'AZURE':
        return _azure_endpoint(sso_config, 'authorize'), None
    if provider == 'GOOGLE':
        return "https://accounts.google.com/o/oauth2/v2/auth", None
    return _oidc_authorization_endpoint(sso_config)


def _authorization_url(auth_endpoint, params):
    """`auth_endpoint` with `params` merged into its existing query."""
    url_parts = list(urllib.parse.urlparse(auth_endpoint))
    query = dict(urllib.parse.parse_qsl(url_parts[4]))
    query.update(params)
    url_parts[4] = urllib.parse.urlencode(query)
    return urllib.parse.urlunparse(url_parts)


def _initiate_oauth(request, provider, organization, sso_config):
    client_id = sso_config.get('client_id')
    if not client_id:
        return _json_error('Client ID is missing', 500)

    redirect_uri = get_service_url(request, provider, organization.id)
    state = _issue_browser_state(request)
    from core.views.agent_login import validate_next
    next_path = validate_next(request.query_params.get('next'))
    # JSON so the OAuth consent flow's `next` can ride the state (the
    # redirect_uri must stay constant for these providers). The callback
    # keeps a plain-string fallback for entries cached before this change.
    cache.set(f"sso_state:{state}",
              json.dumps(dict(org=str(organization.id), next=next_path)),
              timeout=600)  # 10 min TTL

    auth_endpoint, error = _authorization_endpoint(provider, sso_config)
    if error:
        return error
    if not auth_endpoint:
        return _json_error('Could not determine authorization endpoint', 500)

    params = dict(client_id=client_id, response_type='code', redirect_uri=redirect_uri,
                  scope="openid email profile", state=state)
    if provider == 'GOOGLE' and sso_config.get('hosted_domain'):
        params['hd'] = sso_config.get('hosted_domain')
    return HttpResponseRedirect(_authorization_url(auth_endpoint, params))


@extend_schema(
    responses={302: OpenApiResponse(description='Redirect to SSO provider')}
)
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([SSORateThrottle])
def initiate_sso(request, provider):
    """
    Redirects user to the SSO provider's login page.
    Requires 'email' query param to identify the organization (and thus the config),
    OR 'org' ID directly.
    """
    organization, error = _initiate_organization(request)
    if error:
        return error

    rejection = sso_gate_error(organization, provider)
    if rejection:
        message, status_code = rejection
        return _json_error(message, status_code)

    sso_config = organization.sso_config or dict()

    if provider == 'CAS':
        return _initiate_cas(request, organization, sso_config)
    if provider in OAUTH_PROVIDERS:
        return _initiate_oauth(request, provider, organization, sso_config)
    return _json_error(f'Unknown provider {provider}', 400)


@extend_schema(
    responses={302: OpenApiResponse(description='Redirect to frontend with token')}
)
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([SSORateThrottle])
def sso_callback(request, provider):
    """
    Handles the callback from the SSO provider.
    Validates ticket/code, creates session, redirects to frontend.
    """
    frontend_url = getattr(settings, 'CLIENT_URL', 'http://localhost:3000') 
    
    def error_redirect(msg):
        msg = urllib.parse.quote(msg)
        return HttpResponseRedirect(f"{frontend_url}/?error={msg}")

    org_id = request.query_params.get('org')
    if not org_id:
        return error_redirect('Organization ID missing from callback')
        
    try:
        organization = Organization.objects.get(id=org_id)
    except (Organization.DoesNotExist, ValueError, TypeError):
        return error_redirect('Organization not found')

    rejection = sso_gate_error(organization, provider)
    if rejection:
        return error_redirect(rejection[0])

    sso_config = organization.sso_config or {}
    email = None
    # OAuth consent flow: set by the CAS query param or the provider-state JSON.
    oauth_next = None

    # --- CAS VALIDATION ---
    if provider == 'CAS':
        ticket = request.query_params.get('ticket')
        if not ticket:
             return error_redirect('No ticket provided')

        # Refuse a ticket from a login this browser did not start (login CSRF)
        # before spending it at CAS.
        state = request.query_params.get('state')
        state_error = _browser_state_error(request, state)
        if state_error:
            return error_redirect(state_error)

        cas_url = sso_config.get('cas_server_url')
        if not cas_url:
             return error_redirect('CAS Server URL missing')

        cas_version = str(sso_config.get('cas_version', '3'))
        
        # Determine validation endpoint
        validate_path = '/p3/serviceValidate' if cas_version == '3' else '/serviceValidate'
        if cas_version == '2':
             validate_path = '/serviceValidate'
        elif cas_version == '1':
             validate_path = '/validate'
             
        # Reconstruct the EXACT service URL used in initiation (including query
        # params — the raw `next` must round-trip byte-for-byte for CAS).
        service_url = get_service_url(request, provider, org_id,
                                      request.query_params.get('next'), state)
        
        # DERIVE BASE URL FOR VALIDATION
        # If user provided default '/login' URL, strip it to find base.
        validation_base = cas_url.rstrip('/')
        if validation_base.endswith('/login'):
            validation_base = validation_base[:-6]
            
        validation_url = f"{validation_base}{validate_path}"
        params = {'service': service_url, 'ticket': ticket}
        
        try:
            response = requests.get(validation_url, params=params, timeout=10, verify=True)
            
            if response.status_code != 200:
                 logger.error(f"CAS Validation Failed Status: {response.status_code} Body: {response.text}")
                 return error_redirect('Failed to contact CAS server')
                 
            # Parse Response
            if cas_version == '1':
                # CAS 1.0: two lines. First 'yes', second username.
                lines = response.text.splitlines()
                if lines and lines[0].strip() == 'yes':
                    email = lines[1].strip()
            else:
                # CAS 2.0/3.0: XML
                try:
                    root = ET.fromstring(response.content)
                    namespaces = {'cas': 'http://www.yale.edu/tp/cas'}
                    
                    # Try to find success with namespace
                    auth_success = root.find('.//cas:authenticationSuccess', namespaces)
                    if auth_success is not None:
                        user_elem = auth_success.find('cas:user', namespaces)
                        if user_elem is not None:
                            email = user_elem.text
                    else:
                        failure = root.find('.//cas:authenticationFailure', namespaces)
                        if failure is not None:
                             msg = failure.text.strip() if failure.text else "Unknown"
                             logger.error(f"CAS Auth Failure Response: {msg}")
                             return error_redirect("SSO authentication failed. Please try again or contact support.")
                        
                        # Fallback for 'user' tag directly
                        if not email:
                             for elem in root.iter():
                                 if elem.tag.endswith('user'):
                                     email = elem.text
                                     break

                except ET.ParseError as e:
                     logger.error(f"XML Parse Error: {e} Content: {response.text}")
                     return error_redirect('Invalid XML from CAS server')

        except Exception as e:
            logger.error(f"CAS Validation Error: {e}")
            return error_redirect("An error occurred during SSO authentication. Please try again.")
    
    # --- OAUTH VALIDATION (Azure/Google/OIDC) ---
    elif provider in ['AZURE', 'GOOGLE', 'OIDC']:
        # Validate OAuth state parameter to prevent CSRF
        received_state = request.query_params.get('state')
        state_error = _browser_state_error(request, received_state)
        if state_error:
            return error_redirect(state_error)
        cached_state = cache.get(f"sso_state:{received_state}")
        if cached_state is None:
            return error_redirect('Invalid or expired state parameter')
        cache.delete(f"sso_state:{received_state}")  # One-time use
        try:
            state_data = json.loads(cached_state)
        except (TypeError, ValueError):
            state_data = None
        if isinstance(state_data, dict):
            cached_org_id = state_data.get('org')
            oauth_next = state_data.get('next')
        else:
            # Entry cached before the JSON format landed. Note a bare numeric
            # org id ("123") parses as JSON too — hence the isinstance check,
            # not just the except.
            cached_org_id, oauth_next = cached_state, None
        if str(org_id) != cached_org_id:
            return error_redirect('State parameter does not match organization')

        code = request.query_params.get('code')
        if not code:
            return error_redirect('No auth code provided')
            
        client_id = sso_config.get('client_id')
        client_secret = sso_config.get('client_secret')
        redirect_uri = get_service_url(request, provider, org_id)
        
        token_endpoint = ""
        userinfo_endpoint = ""
        
        if provider == 'AZURE':
            tenant = sso_config.get('tenant_id', 'common')
            token_endpoint = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        elif provider == 'GOOGLE':
            token_endpoint = "https://oauth2.googleapis.com/token"
        elif provider == 'OIDC':
            discovery = sso_config.get('discovery_url') 
            try:
                if not discovery:
                    return error_redirect('Discovery URL missing')
                resp = requests.get(discovery, timeout=5).json()
                token_endpoint = resp.get('token_endpoint')
                userinfo_endpoint = resp.get('userinfo_endpoint')
            except Exception as e:
                logger.error(f"OIDC discovery failed in callback: {e}")
                return error_redirect('OIDC discovery failed in callback')

        if not token_endpoint:
             return error_redirect('Token endpoint not found')
             
        # Exchange Code for Token
        data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }
        
        try:
            token_resp = requests.post(token_endpoint, data=data, timeout=10)
            if token_resp.status_code != 200:
                logger.error(f"Token Exchange Failed: {token_resp.text}")
                return error_redirect('Failed to exchange code for token')
            
            tokens = token_resp.json()
            access_token = tokens.get('access_token')
            id_token = tokens.get('id_token')
            
            # Extract Email logic ...
            if provider == 'GOOGLE':
                 userinfo_resp = requests.get('https://www.googleapis.com/oauth2/v3/userinfo', 
                                    headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
                 if userinfo_resp.status_code == 200:
                     email = userinfo_resp.json().get('email')
                     
            elif provider == 'AZURE':
                 graph_resp = requests.get('https://graph.microsoft.com/v1.0/me',
                                    headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
                 if graph_resp.status_code == 200:
                     data = graph_resp.json()
                     email = data.get('mail') or data.get('userPrincipalName')

            elif provider == 'OIDC':
                 if userinfo_endpoint:
                     u_resp = requests.get(userinfo_endpoint, headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
                     if u_resp.status_code == 200:
                         email = u_resp.json().get('email')
            
            if not email and id_token:
                try:
                    import base64
                    parts = id_token.split('.')
                    if len(parts) > 1:
                        payload = parts[1]
                        payload += '=' * (-len(payload) % 4)
                        decoded = json.loads(base64.b64decode(payload).decode('utf-8'))
                        email = decoded.get('email') or decoded.get('preferred_username')
                except Exception as e:
                    logger.error(f"ID Token decode error: {e}")

        except Exception as e:
            logger.error(f"OAuth Error: {e}")
            return error_redirect("An error occurred during SSO authentication. Please try again.")

    # --- OTHER PROVIDERS ---
    else:
        return error_redirect(f"Provider {provider} not supported yet in callback")

    if not email:
        return error_redirect('Could not extract user identity from SSO response')

    # Heuristic: If email is just a username (no @), append org domain if available
    # This handles CAS servers that return NetIDs instead of emails
    if '@' not in email and organization.email_domain:
        email = f"{email}@{organization.email_domain}"

    # --- USER RESOLUTION & LOGIN ---
    # We trust the SSO provider. Get or create the user.
    # Note: get_or_create_user handles auto-activation if sso_enabled is True
    user = get_or_create_user(email, organization, auto_activate=True)
    
    if not user:
         return error_redirect('Failed to create/retrieve user locally')

    # OAuth consent flow (agent connections): when a validated local
    # /o/authorize `next` rode the SSO round-trip, finish with a short-lived
    # Django session on the API origin and hand the browser back to the consent
    # page. Everything below this block — the normal SPA JWT redirect — is
    # untouched when no `next` is present.
    from core.views.agent_login import (SESSION_LIFETIME_SECONDS, validate_next)

    if provider == 'CAS':
        oauth_next = request.query_params.get('next')
    oauth_next = validate_next(oauth_next)
    if oauth_next:
        from django.contrib.auth import login as auth_login
        # Explicit backend: the user was resolved from the SSO assertion, not
        # via authenticate(), so Django can't infer one.
        auth_login(request, user,
                   backend='django.contrib.auth.backends.ModelBackend')
        request.session.set_expiry(SESSION_LIFETIME_SECONDS)
        return HttpResponseRedirect(oauth_next)

    # Generate a short-lived access token to hand off via the redirect URL. The
    # refresh token is NOT put in the URL — the frontend exchanges this access
    # token for a refresh token via the current_user endpoint after landing.
    from core.views.auth import access_token_for_user

    token = access_token_for_user(user)

    # Redirect to Frontend
    # In production, frontend is served by Nginx.
    frontend_url = getattr(settings, 'CLIENT_URL', 'http://localhost:3000') # Default for dev
    return HttpResponseRedirect(f"{frontend_url}/?token={token}")


@extend_schema(responses={200: CheckSSOAvailabilityResponseSerializer})
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([SSORateThrottle])
def check_sso_availability(request):
    """
    Checks if the given email belongs to an SSO-enabled organization.
    Returns { "sso_enabled": true, "provider": "CAS", "org_id": 123 } 
    or { "sso_enabled": false }
    """
    email = request.query_params.get('email')
    if not email:
        return JsonResponse({'error': 'Email is required'}, status=400)
        
    organization = None
    
    # 1. Try by domain
    domain = email.split('@')[-1]
    
    # HEURISTIC: Check explicit domain mapping first (primary + allowed domains)
    organization = get_organization_by_email_domain(domain, sso_enabled=True)
    
    # 2. If no domain match, check user mapping
    if not organization:
        user_org = _organization_of_unique_user(email)
        if user_org and user_org.sso_enabled:
            organization = user_org
            
    if organization and organization.sso_enabled:
        return JsonResponse({
            'sso_enabled': True,
            'provider': organization.sso_provider,
            'org_id': organization.id,
            'org_name': organization.name
        })
        
    return JsonResponse({'sso_enabled': False})


@extend_schema(responses={200: MainOrgSSOConfigSerializer})
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([SSORateThrottle])
def get_sso_config(request):
    """
    Returns SSO configuration for the main/default organization.
    Used by the frontend to auto-redirect to SSO on the default login page.
    """
    from core.models import get_main_org
    organization = get_main_org()

    if not organization:
        return JsonResponse({'main_org': False})

    response = {
        'main_org': True,
        'sso_enabled': organization.sso_enabled,
        'org_id': organization.id,
        'org_name': organization.name,
    }
    if organization.sso_enabled:
        response['provider'] = organization.sso_provider
    return JsonResponse(response)


@extend_schema(responses={200: OrgSSOConfigSerializer})
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([SSORateThrottle])
def get_org_sso_config(request, shortname):
    """
    Returns SSO configuration for a specific organization by shortname.
    Used by the frontend for per-org login pages (e.g. /login/RU).
    """
    organization = Organization.objects.filter(shortname__iexact=shortname).first()

    if not organization:
        return JsonResponse({'error': 'Organization not found'}, status=404)

    response = {
        'found': True,
        'sso_enabled': organization.sso_enabled,
        'org_id': organization.id,
        'org_name': organization.name,
    }
    if organization.sso_enabled:
        response['provider'] = organization.sso_provider
    return JsonResponse(response)
