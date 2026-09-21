# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.test import SimpleTestCase, RequestFactory
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from core.views.sso import sso_callback, initiate_sso, get_organization_by_email_domain

from core.models import Organization

class SSOTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        
        # Mock Org Data
        self.org_mock = MagicMock()
        self.org_mock.id = 1
        self.org_mock.name = "Test Org"
        self.org_mock.shortname = "testorg"
        self.org_mock.email_domain = "test.edu"
        self.org_mock.sso_enabled = True
        self.org_mock.sso_provider = "CAS"
        self.org_mock.sso_config = {"cas_server_url": "https://cas.test.edu"}

    @patch('core.views.sso.Organization.objects.get')
    def test_sso_initiate_no_org(self, mock_get_org):
        mock_get_org.side_effect = Organization.DoesNotExist("DoesNotExist")
        
        request = self.factory.get('/auth/sso/login/CAS/', {'org': '999'})
        response = initiate_sso(request, 'CAS')
        self.assertEqual(response.status_code, 404)

    @patch('core.views.sso.Organization.objects.get')
    def test_sso_initiate_cas(self, mock_get_org):
        mock_get_org.return_value = self.org_mock
        
        request = self.factory.get('/auth/sso/login/CAS/', {'org': '1'})
        response = initiate_sso(request, 'CAS')
        self.assertEqual(response.status_code, 302)
        self.assertTrue("https://cas.test.edu" in response.url)

    @patch('core.views.sso.get_or_create_user')
    @patch('core.views.sso.requests.get')
    @patch('core.views.sso.Organization.objects.get')
    def test_sso_callback_cas_success(self, mock_get_org, mock_requests_get, mock_get_create_user):
        mock_get_org.return_value = self.org_mock
        
        # Mock CAS Response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"""<cas:serviceResponse xmlns:cas='http://www.yale.edu/tp/cas'>
            <cas:authenticationSuccess>
                <cas:user>student@test.edu</cas:user>
            </cas:authenticationSuccess>
        </cas:serviceResponse>"""
        mock_requests_get.return_value = mock_response

        # Mock User
        mock_user = MagicMock()
        mock_get_create_user.return_value = mock_user
        
        # Mock JWT Token generation (since we can't import RefreshToken easily without DB sometimes)
        with patch('core.views.auth.access_token_for_user') as mock_token_fn:
            mock_token_fn.return_value = "fake_token"
            
            request = self.factory.get('/auth/sso/callback/CAS/', {'org': '1', 'ticket': 'ST-12345'})
            response = sso_callback(request, 'CAS')
            
            self.assertEqual(response.status_code, 302)
            self.assertTrue("token=fake_token" in response.url)
            # userinfo lookups must be bounded so a slow IdP cannot hang the request thread
            self.assertEqual(mock_requests_get.call_args.kwargs['timeout'], 10)

    @patch('core.views.sso.get_or_create_user')
    @patch('core.views.sso.requests.get')
    @patch('core.views.sso.Organization.objects.get')
    def test_sso_callback_cas_username_only(self, mock_get_org, mock_requests_get, mock_get_create_user):
        mock_get_org.return_value = self.org_mock
        
        # Mock CAS Response with Username
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"""<cas:serviceResponse xmlns:cas='http://www.yale.edu/tp/cas'>
            <cas:authenticationSuccess>
                <cas:user>student</cas:user>
            </cas:authenticationSuccess>
        </cas:serviceResponse>"""
        mock_requests_get.return_value = mock_response

        # Setup mock behavior to verify email argument
        def side_effect(email, org, auto_activate):
            self.assertEqual(email, "student@test.edu") # Check if domain appended
            return MagicMock()
            
        mock_get_create_user.side_effect = side_effect
        
        with patch('core.views.auth.access_token_for_user') as mock_token_fn:
            mock_token_fn.return_value = "fake_token"
            
            request = self.factory.get('/auth/sso/callback/CAS/', {'org': '1', 'ticket': 'ST-12345'})
            response = sso_callback(request, 'CAS')
            
            self.assertEqual(response.status_code, 302)

    @patch('core.views.sso.get_or_create_user')
    @patch('core.views.sso.requests.post')
    @patch('core.views.sso.requests.get')
    @patch('core.views.sso.Organization.objects.get')
    def test_sso_callback_azure_success(self, mock_get_org, mock_requests_get, mock_requests_post, mock_get_create_user):
        self.org_mock.sso_provider = "AZURE"
        self.org_mock.sso_config = {
            "tenant_id": "common", 
            "client_id": "client123", 
            "client_secret": "secret"
        }
        mock_get_org.return_value = self.org_mock

        # Mock Token Exchange
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "fake_access_token",
            "id_token": "fake_id_token"
        }
        mock_requests_post.return_value = mock_token_resp

        # Mock Graph API
        mock_graph_resp = MagicMock()
        mock_graph_resp.status_code = 200
        mock_graph_resp.json.return_value = {"mail": "azureUser@test.edu"}
        mock_requests_get.return_value = mock_graph_resp
        
        mock_get_create_user.return_value = MagicMock()

        with patch('core.views.auth.access_token_for_user') as mock_token_fn:
            mock_token_fn.return_value = "fake_token"

            # Set up state in cache to pass CSRF validation
            cache.set('sso_state:test_azure_state', '1', timeout=600)
            request = self.factory.get('/auth/sso/callback/AZURE/', {'org': '1', 'code': 'auth_code', 'state': 'test_azure_state'})
            response = sso_callback(request, 'AZURE')
            
            self.assertEqual(response.status_code, 302)
            self.assertTrue("token=fake_token" in response.url)
            # userinfo lookups must be bounded so a slow IdP cannot hang the request thread
            self.assertEqual(mock_requests_get.call_args.kwargs['timeout'], 10)

    @patch('core.views.sso.get_or_create_user')
    @patch('core.views.sso.requests.post')
    @patch('core.views.sso.requests.get')
    @patch('core.views.sso.Organization.objects.get')
    def test_sso_callback_google_success(self, mock_get_org, mock_requests_get, mock_requests_post, mock_get_create_user):
        self.org_mock.sso_provider = "GOOGLE"
        self.org_mock.sso_config = {
            "client_id": "googleconf", 
            "client_secret": "googlesecret"
        }
        mock_get_org.return_value = self.org_mock

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "google_access_token", "id_token": "google_id_token"}
        mock_requests_post.return_value = mock_token_resp

        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.status_code = 200
        mock_userinfo_resp.json.return_value = {"email": "googleUser@test.edu"}
        mock_requests_get.return_value = mock_userinfo_resp
        
        mock_get_create_user.return_value = MagicMock()

        with patch('core.views.auth.access_token_for_user') as mock_token_fn:
            mock_token_fn.return_value = "fake_token"

            # Set up state in cache to pass CSRF validation
            cache.set('sso_state:test_google_state', '1', timeout=600)
            request = self.factory.get('/auth/sso/callback/GOOGLE/', {'org': '1', 'code': 'google_code', 'state': 'test_google_state'})
            response = sso_callback(request, 'GOOGLE')
            
            self.assertEqual(response.status_code, 302)
            self.assertTrue("token=fake_token" in response.url)
            # userinfo lookups must be bounded so a slow IdP cannot hang the request thread
            self.assertEqual(mock_requests_get.call_args.kwargs['timeout'], 10)


class GetOrganizationByEmailDomainTest(SimpleTestCase):
    """Tests for the get_organization_by_email_domain helper function."""

    def setUp(self):
        self.org_primary = MagicMock()
        self.org_primary.id = 1
        self.org_primary.email_domain = "rutgers.edu"
        self.org_primary.allowed_email_domains = ["scarletmail.rutgers.edu", "cs.rutgers.edu"]
        self.org_primary.sso_enabled = True

        self.org_other = MagicMock()
        self.org_other.id = 2
        self.org_other.email_domain = "princeton.edu"
        self.org_other.allowed_email_domains = []
        self.org_other.sso_enabled = True

    @patch('core.views.sso.Organization.objects')
    def test_primary_domain_match(self, mock_objects):
        """Primary email_domain should match directly via ORM filter."""
        mock_objects.filter.return_value.first.return_value = self.org_primary
        result = get_organization_by_email_domain("rutgers.edu")
        self.assertEqual(result, self.org_primary)
        mock_objects.filter.assert_called_once_with(email_domain="rutgers.edu")

    @patch('core.views.sso.Organization.objects')
    def test_allowed_domain_match(self, mock_objects):
        """A domain in allowed_email_domains should match via fallback."""
        # Primary lookup returns nothing
        mock_objects.filter.return_value.first.return_value = None
        # Fallback iterates all orgs
        mock_objects.filter.return_value.__iter__ = MagicMock(
            return_value=iter([self.org_primary, self.org_other])
        )
        result = get_organization_by_email_domain("scarletmail.rutgers.edu")
        self.assertEqual(result, self.org_primary)

    @patch('core.views.sso.Organization.objects')
    def test_no_match_returns_none(self, mock_objects):
        """An unrecognized domain should return None."""
        mock_objects.filter.return_value.first.return_value = None
        mock_objects.filter.return_value.__iter__ = MagicMock(
            return_value=iter([self.org_primary, self.org_other])
        )
        result = get_organization_by_email_domain("unknown.edu")
        self.assertIsNone(result)

    @patch('core.views.sso.Organization.objects')
    def test_allowed_domain_with_extra_filters(self, mock_objects):
        """Extra filters (e.g. sso_enabled=True) should be passed through."""
        mock_objects.filter.return_value.first.return_value = None
        mock_objects.filter.return_value.__iter__ = MagicMock(
            return_value=iter([self.org_primary])
        )
        result = get_organization_by_email_domain("cs.rutgers.edu", sso_enabled=True)
        self.assertEqual(result, self.org_primary)
        # Both calls should include sso_enabled=True
        calls = mock_objects.filter.call_args_list
        self.assertEqual(calls[0].kwargs.get('sso_enabled'), True)

    @patch('core.views.sso.Organization.objects')
    def test_empty_allowed_domains_no_match(self, mock_objects):
        """Org with empty allowed_email_domains shouldn't match non-primary domains."""
        mock_objects.filter.return_value.first.return_value = None
        mock_objects.filter.return_value.__iter__ = MagicMock(
            return_value=iter([self.org_other])
        )
        result = get_organization_by_email_domain("mail.princeton.edu")
        self.assertIsNone(result)


class SSOInitiateAllowedDomainsTest(SimpleTestCase):
    """Tests that initiate_sso works with allowed_email_domains."""

    def setUp(self):
        self.factory = RequestFactory()
        self.org_mock = MagicMock()
        self.org_mock.id = 1
        self.org_mock.name = "Rutgers"
        self.org_mock.email_domain = "rutgers.edu"
        self.org_mock.allowed_email_domains = ["scarletmail.rutgers.edu"]
        self.org_mock.sso_enabled = True
        self.org_mock.sso_provider = "CAS"
        self.org_mock.sso_config = {"cas_server_url": "https://cas.rutgers.edu"}

    @patch('core.views.sso.get_organization_by_email_domain')
    def test_initiate_sso_with_subdomain_email(self, mock_get_org):
        """SSO initiation with a subdomain email should find the correct org."""
        mock_get_org.return_value = self.org_mock

        request = self.factory.get('/auth/sso/login/CAS/', {'email': 'student@scarletmail.rutgers.edu'})
        response = initiate_sso(request, 'CAS')

        self.assertEqual(response.status_code, 302)
        self.assertIn("https://cas.rutgers.edu", response.url)
        mock_get_org.assert_called_once_with("scarletmail.rutgers.edu")

    @patch('core.views.sso.get_organization_by_email_domain')
    @patch('core.views.sso.User.objects.get')
    def test_initiate_sso_unknown_domain_falls_to_user_lookup(self, mock_user_get, mock_get_org):
        """If domain is not in primary or allowed, it falls back to user profile lookup."""
        mock_get_org.return_value = None
        mock_user = MagicMock()
        mock_user.profile.organization = self.org_mock
        mock_user_get.return_value = mock_user

        request = self.factory.get('/auth/sso/login/CAS/', {'email': 'student@personal.com'})
        response = initiate_sso(request, 'CAS')

        self.assertEqual(response.status_code, 302)
        mock_get_org.assert_called_once_with("personal.com")

