# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.http import HttpResponseRedirect, JsonResponse
from rest_framework.decorators import api_view, permission_classes, renderer_classes
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse
from core.serializers.sso import CheckSSOAvailabilityResponseSerializer
from django.conf import settings
from core.models import Organization, User
from core.utils import get_or_create_user
from core.views.auth import JWTSerializer
import requests
import urllib.parse
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)

# Helper to get service URL
def get_service_url(request, provider, org_id=None):
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
    return url

@extend_schema(
    responses={302: OpenApiResponse(description='Redirect to SSO provider')}
)
@api_view(['GET'])
@permission_classes([AllowAny])
def initiate_sso(request, provider):
    """
    Redirects user to the SSO provider's login page.
    Requires 'email' query param to identify the organization (and thus the config),
    OR 'org' ID directly.
    """
    email = request.query_params.get('email')
    org_id = request.query_params.get('org')
    
    organization = None
    
    if org_id:
        try:
            organization = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            return JsonResponse({'error': 'Organization not found'}, status=404)
    elif email:
        domain = email.split('@')[-1]
        try:
            organization = Organization.objects.filter(email_domain=domain).first()
        except:
            pass
            
        if not organization: 
            try:
                user = User.objects.get(email=email)
                organization = user.profile.organization
            except User.DoesNotExist:
                pass

    if not organization:
        return JsonResponse({'error': 'Could not determine organization for SSO'}, status=400)

    if not organization.sso_enabled:
        return JsonResponse({'error': 'SSO is not enabled for this organization'}, status=403)
        
    sso_config = organization.sso_config or {}
    target_provider = organization.sso_provider
    if target_provider != provider:
        return JsonResponse({'error': f'Organization is configured for {target_provider}, not {provider}'}, status=400)

    # 1. CAS Logic
    if provider == 'CAS':
        cas_url = sso_config.get('cas_server_url')
        if not cas_url:
            return JsonResponse({'error': 'CAS Server URL is missing from config'}, status=500)
            
        # Pass org_id to service URL so we can retrieve config on callback
        service_url = get_service_url(request, provider, organization.id)
        encoded_service = urllib.parse.quote(service_url)
        
        # USE PROVIDED URL AS LOGIN ENDPOINT DIRECTLY (per user request)
        separator = '&' if '?' in cas_url else '?'
        redirect_url = f"{cas_url}{separator}service={encoded_service}"
        return HttpResponseRedirect(redirect_url)

    # 2. OAuth Logic (Azure, Google, OIDC)
    elif provider in ['AZURE', 'GOOGLE', 'OIDC']:
        client_id = sso_config.get('client_id')
        if not client_id:
            return JsonResponse({'error': 'Client ID is missing'}, status=500)
            
        scopes = "openid email profile"
        redirect_uri = get_service_url(request, provider, organization.id)
        state = "random_state_string" # Should use session/cache to verify state
        
        auth_endpoint = ""
        
        if provider == 'AZURE':
            tenant = sso_config.get('tenant_id', 'common')
            auth_endpoint = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
        elif provider == 'GOOGLE':
            auth_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
            hd = sso_config.get('hosted_domain')
            if hd:
                # Optimized for Google Hosted Domain
                pass 
        elif provider == 'OIDC':
            discovery = sso_config.get('discovery_url')
            if not discovery:
                return JsonResponse({'error': 'Discovery URL missing'}, status=500)
            try:
                resp = requests.get(discovery, timeout=5).json()
                auth_endpoint = resp.get('authorization_endpoint')
            except Exception as e:
                return JsonResponse({'error': f'Failed to fetch OIDC config: {e}'}, status=500)
                
        if not auth_endpoint:
            return JsonResponse({'error': 'Could not determine authorization endpoint'}, status=500)
            
        params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'scope': scopes,
            'state': state,
        }
        if provider == 'GOOGLE' and sso_config.get('hosted_domain'):
            params['hd'] = sso_config.get('hosted_domain')
            
        url_parts = list(urllib.parse.urlparse(auth_endpoint))
        query = dict(urllib.parse.parse_qsl(url_parts[4]))
        query.update(params)
        url_parts[4] = urllib.parse.urlencode(query)
        full_auth_url = urllib.parse.urlunparse(url_parts)
        
        return HttpResponseRedirect(full_auth_url)

    return JsonResponse({'error': f'Unknown provider {provider}'}, status=400)


@extend_schema(
    responses={302: OpenApiResponse(description='Redirect to frontend with token')}
)
@api_view(['GET'])
@permission_classes([AllowAny])
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
    except Organization.DoesNotExist:
        return error_redirect('Organization not found')

    sso_config = organization.sso_config or {}
    email = None

    # --- CAS VALIDATION ---
    if provider == 'CAS':
        ticket = request.query_params.get('ticket')
        if not ticket:
             return error_redirect('No ticket provided')

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
             
        # Reconstruct the EXACT service URL used in initiation (including query params)
        service_url = get_service_url(request, provider, org_id)
        
        # DERIVE BASE URL FOR VALIDATION
        # If user provided default '/login' URL, strip it to find base.
        validation_base = cas_url.rstrip('/')
        if validation_base.endswith('/login'):
            validation_base = validation_base[:-6]
            
        validation_url = f"{validation_base}{validate_path}"
        params = {'service': service_url, 'ticket': ticket}
        
        try:
            # Disable SSL verification for debug to support localhost self-signed certs
            verify_ssl = not settings.DEBUG
            response = requests.get(validation_url, params=params, timeout=10, verify=verify_ssl)
            
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
                             return error_redirect(f"CAS Authentication Failed: {msg}")
                        
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
            return error_redirect(f"Internal Error during CAS validation: {str(e)}")
    
    # --- OAUTH VALIDATION (Azure/Google/OIDC) ---
    elif provider in ['AZURE', 'GOOGLE', 'OIDC']:
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
            except:
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
                                    headers={'Authorization': f'Bearer {access_token}'})
                 if userinfo_resp.status_code == 200:
                     email = userinfo_resp.json().get('email')
                     
            elif provider == 'AZURE':
                 graph_resp = requests.get('https://graph.microsoft.com/v1.0/me',
                                    headers={'Authorization': f'Bearer {access_token}'})
                 if graph_resp.status_code == 200:
                     data = graph_resp.json()
                     email = data.get('mail') or data.get('userPrincipalName')

            elif provider == 'OIDC':
                 if userinfo_endpoint:
                     u_resp = requests.get(userinfo_endpoint, headers={'Authorization': f'Bearer {access_token}'})
                     if u_resp.status_code == 200:
                         email = u_resp.json().get('email')
            
            if not email and id_token:
                try:
                    import json
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

    # Generate JWT
    from rest_framework_simplejwt.tokens import RefreshToken
    
    refresh = RefreshToken.for_user(user)
    token = str(refresh.access_token)
    
    # Redirect to Frontend
    # In production, frontend is served by Nginx. 
    frontend_url = getattr(settings, 'CLIENT_URL', 'http://localhost:3000') # Default for dev
    return HttpResponseRedirect(f"{frontend_url}/?token={token}")


@extend_schema(responses={200: CheckSSOAvailabilityResponseSerializer})
@api_view(['GET'])
@permission_classes([AllowAny])
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
    
    # HEURISTIC: Check explicit domain mapping first
    # Note: emailDomain in Organization model might be a string or list? 
    # Based on OrganizationSerializer it seemed like a string.
    # But let's check exact match for now.
    organization = Organization.objects.filter(email_domain=domain, sso_enabled=True).first()
    
    # 2. If no domain match, check user mapping
    if not organization:
        try:
            user = User.objects.get(email=email)
            if user.profile.organization and user.profile.organization.sso_enabled:
                organization = user.profile.organization
        except User.DoesNotExist:
            pass
            
    if organization and organization.sso_enabled:
        return JsonResponse({
            'sso_enabled': True,
            'provider': organization.sso_provider,
            'org_id': organization.id,
            'org_name': organization.name
        })
        
    return JsonResponse({'sso_enabled': False})
