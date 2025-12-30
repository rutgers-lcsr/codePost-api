from django.test import SimpleTestCase, RequestFactory
from django.urls import reverse
from unittest.mock import patch, MagicMock
from core.views.sso import sso_callback, initiate_sso
from django.conf import settings
import json

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
        with patch('rest_framework_simplejwt.tokens.RefreshToken.for_user') as mock_refresh:
            mock_token = MagicMock()
            mock_token.access_token = "fake_token"
            mock_refresh.return_value = mock_token
            
            request = self.factory.get('/auth/sso/callback/CAS/', {'org': '1', 'ticket': 'ST-12345'})
            response = sso_callback(request, 'CAS')
            
            self.assertEqual(response.status_code, 302)
            self.assertTrue("token=fake_token" in response.url)

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
        
        with patch('rest_framework_simplejwt.tokens.RefreshToken.for_user') as mock_refresh:
            mock_token = MagicMock()
            mock_token.access_token = "fake_token"
            mock_refresh.return_value = mock_token
            
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

        with patch('rest_framework_simplejwt.tokens.RefreshToken.for_user') as mock_refresh:
            mock_token = MagicMock()
            mock_token.access_token = "fake_token"
            mock_refresh.return_value = mock_token

            request = self.factory.get('/auth/sso/callback/AZURE/', {'org': '1', 'code': 'auth_code'})
            response = sso_callback(request, 'AZURE')
            
            self.assertEqual(response.status_code, 302)
            self.assertTrue("token=fake_token" in response.url)

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

        with patch('rest_framework_simplejwt.tokens.RefreshToken.for_user') as mock_refresh:
            mock_token = MagicMock()
            mock_token.access_token = "fake_token"
            mock_refresh.return_value = mock_token

            request = self.factory.get('/auth/sso/callback/GOOGLE/', {'org': '1', 'code': 'google_code'})
            response = sso_callback(request, 'GOOGLE')
            
            self.assertEqual(response.status_code, 302)
            self.assertTrue("token=fake_token" in response.url)

