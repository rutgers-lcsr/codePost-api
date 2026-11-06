# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Pins every branch of initiate_sso and sso_callback (CAS, AZURE, GOOGLE, OIDC): exact
redirect URLs, error messages, status codes, and the arguments of the outbound IdP calls.
These guard login, so a refactor must leave all of it byte-identical. Only the HTTP calls
to the IdP are mocked; organizations, sessions, cache and users are real."""
import base64
import json
import urllib.parse
from unittest.mock import MagicMock, call, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from core.models import Organization

NEXT = "/o/authorize/?client_id=abc&state=xyz"
CAS_NS = "http://www.yale.edu/tp/cas"
GENERIC = "An error occurred during SSO authentication. Please try again."
NO_IDENTITY = "Could not extract user identity from SSO response"


def err(message):
  return f"{settings.CLIENT_URL}/?error={urllib.parse.quote(message)}"


def cas_xml(inner):
  return f"<cas:serviceResponse xmlns:cas='{CAS_NS}'>{inner}</cas:serviceResponse>".encode()


def cas_ok(user="someone"):
  return cas_xml(f"<cas:authenticationSuccess><cas:user>{user}</cas:user></cas:authenticationSuccess>")


def jwt_with(payload):
  body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
  return f"h.{body}.s"


def make_org(provider, config, **fields):
  values = dict(name=f"{provider} Org", shortname=provider.lower(), email_domain="idp.edu",
                sso_enabled=True, sso_provider=provider, sso_config=config)
  values.update(fields)
  return Organization.objects.create(**values)


def login_state(client, state="s1"):
  """Mark `state` as issued to this client's browser."""
  session = client.session
  session[f"sso_state:{state}"] = True
  session.save()


def error_of(resp):
  return resp.status_code, resp.json()["error"]


class InitiateSSOTests(APITestCase):

  def _location_query(self, resp):
    return urllib.parse.parse_qs(urllib.parse.urlparse(resp["Location"]).query)

  def _cas_org(self, **fields):
    return make_org("CAS", dict(cas_server_url="https://cas.idp.edu/cas/login"), **fields)

  def test_missing_identifiers_cannot_determine_the_organization(self):
    resp = self.client.get("/auth/sso/login/CAS/")
    self.assertEqual(error_of(resp), (400, "Could not determine organization for SSO"))

  def test_non_numeric_org_is_not_found(self):
    resp = self.client.get("/auth/sso/login/CAS/", dict(org="abc"))
    self.assertEqual(error_of(resp), (404, "Organization not found"))

  def test_unknown_email_domain_cannot_determine_the_organization(self):
    resp = self.client.get("/auth/sso/login/CAS/", dict(email="x@nowhere.test"))
    self.assertEqual(resp.status_code, 400)

  def test_email_resolves_the_organization_by_domain(self):
    org = self._cas_org()
    resp = self.client.get("/auth/sso/login/CAS/", dict(email="x@idp.edu"))
    self.assertEqual(resp.status_code, 302)
    self.assertIn(urllib.parse.quote(f"?org={org.id}&state=", safe=""), resp["Location"])

  def test_email_resolves_the_organization_through_its_one_user(self):
    org = self._cas_org(email_domain="other.edu")
    user = User.objects.create(username="u", email="u@elsewhere.test")
    user.profile.organization = org
    user.profile.save()
    resp = self.client.get("/auth/sso/login/CAS/", dict(email="u@elsewhere.test"))
    self.assertEqual(resp.status_code, 302)
    self.assertIn(urllib.parse.quote(f"?org={org.id}&state=", safe=""), resp["Location"])

  def test_sso_disabled_is_forbidden(self):
    org = make_org("CAS", dict(), sso_enabled=False)
    resp = self.client.get("/auth/sso/login/CAS/", dict(org=org.id))
    self.assertEqual(error_of(resp), (403, "SSO is not enabled for this organization"))

  def test_provider_mismatch_is_a_bad_request(self):
    org = make_org("AZURE", dict())
    resp = self.client.get("/auth/sso/login/CAS/", dict(org=org.id))
    self.assertEqual(error_of(resp), (400, "Organization is configured for AZURE, not CAS"))

  def test_unknown_provider_is_a_bad_request(self):
    org = make_org("LDAP", dict())
    resp = self.client.get("/auth/sso/login/LDAP/", dict(org=org.id))
    self.assertEqual(error_of(resp), (400, "Unknown provider LDAP"))

  def test_cas_without_server_url_is_a_500(self):
    org = make_org("CAS", dict())
    resp = self.client.get("/auth/sso/login/CAS/", dict(org=org.id))
    self.assertEqual(error_of(resp), (500, "CAS Server URL is missing from config"))
    self.assertEqual([k for k in self.client.session.keys() if k.startswith("sso_state:")], [])

  def test_cas_redirect_is_exact(self):
    org = self._cas_org()
    resp = self.client.get("/auth/sso/login/CAS/", dict(org=org.id))
    [key] = [k for k in self.client.session.keys() if k.startswith("sso_state:")]
    state = key.split(":", 1)[1]
    service = f"https://testserver/auth/sso/callback/CAS/?org={org.id}&state={state}"
    self.assertEqual(resp["Location"], f"https://cas.idp.edu/cas/login?service={urllib.parse.quote(service)}")

  def test_cas_server_url_with_a_query_joins_with_an_ampersand(self):
    org = make_org("CAS", dict(cas_server_url="https://cas.idp.edu/login?x=1"))
    resp = self.client.get("/auth/sso/login/CAS/", dict(org=org.id))
    self.assertTrue(resp["Location"].startswith("https://cas.idp.edu/login?x=1&service="))

  def test_cas_threads_a_valid_next_and_drops_an_invalid_one(self):
    org = self._cas_org()
    resp = self.client.get("/auth/sso/login/CAS/", dict(org=org.id, next=NEXT))
    service = self._location_query(resp)["service"][0]
    self.assertIn(f"?org={org.id}&next={urllib.parse.quote(NEXT, safe='')}&state=", service)
    resp = self.client.get("/auth/sso/login/CAS/", dict(org=org.id, next="https://evil.test/o/authorize"))
    self.assertNotIn("next=", self._location_query(resp)["service"][0])

  @override_settings(DEBUG=True)
  def test_service_url_keeps_the_request_scheme_when_debugging(self):
    org = self._cas_org()
    resp = self.client.get("/auth/sso/login/CAS/", dict(org=org.id))
    self.assertTrue(self._location_query(resp)["service"][0].startswith("http://testserver/"))

  def test_service_url_is_https_when_not_debugging(self):
    org = self._cas_org()
    resp = self.client.get("/auth/sso/login/CAS/", dict(org=org.id))
    self.assertTrue(self._location_query(resp)["service"][0].startswith("https://testserver/"))

  def test_oauth_without_client_id_is_a_500(self):
    org = make_org("AZURE", dict())
    resp = self.client.get("/auth/sso/login/AZURE/", dict(org=org.id))
    self.assertEqual(error_of(resp), (500, "Client ID is missing"))

  def _state_of(self, resp):
    return self._location_query(resp)["state"][0]

  def _expected(self, endpoint, org, provider, state, extra=""):
    redirect = urllib.parse.quote(f"https://testserver/auth/sso/callback/{provider}/?org={org.id}", safe="")
    return (f"{endpoint}?client_id=cid&response_type=code&redirect_uri={redirect}"
            f"&scope=openid+email+profile&state={state}{extra}")

  def test_azure_redirect_is_exact_and_caches_the_state(self):
    org = make_org("AZURE", dict(client_id="cid", tenant_id="tnt"))
    resp = self.client.get("/auth/sso/login/AZURE/", dict(org=org.id, next=NEXT))
    state = self._state_of(resp)
    self.assertEqual(resp["Location"], self._expected(
      "https://login.microsoftonline.com/tnt/oauth2/v2.0/authorize", org, "AZURE", state))
    self.assertEqual(json.loads(cache.get(f"sso_state:{state}")), dict(org=str(org.id), next=NEXT))
    self.assertTrue(self.client.session[f"sso_state:{state}"])

  def test_azure_tenant_defaults_to_common_and_next_to_null(self):
    org = make_org("AZURE", dict(client_id="cid"))
    resp = self.client.get("/auth/sso/login/AZURE/", dict(org=org.id))
    state = self._state_of(resp)
    self.assertTrue(resp["Location"].startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?"))
    self.assertEqual(json.loads(cache.get(f"sso_state:{state}")), dict(org=str(org.id), next=None))

  def test_google_redirect_with_and_without_hosted_domain(self):
    org = make_org("GOOGLE", dict(client_id="cid", hosted_domain="idp.edu"))
    resp = self.client.get("/auth/sso/login/GOOGLE/", dict(org=org.id))
    self.assertEqual(resp["Location"], self._expected(
      "https://accounts.google.com/o/oauth2/v2/auth", org, "GOOGLE", self._state_of(resp), "&hd=idp.edu"))
    org.sso_config = dict(client_id="cid")
    org.save()
    resp = self.client.get("/auth/sso/login/GOOGLE/", dict(org=org.id))
    self.assertEqual(resp["Location"], self._expected(
      "https://accounts.google.com/o/oauth2/v2/auth", org, "GOOGLE", self._state_of(resp)))

  def test_oidc_without_discovery_url_is_a_500(self):
    org = make_org("OIDC", dict(client_id="cid"))
    resp = self.client.get("/auth/sso/login/OIDC/", dict(org=org.id))
    self.assertEqual(error_of(resp), (500, "Discovery URL missing"))

  def test_oidc_discovery_failure_is_a_500_naming_the_error(self):
    org = make_org("OIDC", dict(client_id="cid", discovery_url="https://idp/.well-known"))
    with patch("core.views.sso.requests.get", side_effect=RuntimeError("boom")):
      resp = self.client.get("/auth/sso/login/OIDC/", dict(org=org.id))
    self.assertEqual(error_of(resp), (500, "Failed to fetch OIDC config: boom"))

  def test_oidc_without_authorization_endpoint_is_a_500(self):
    org = make_org("OIDC", dict(client_id="cid", discovery_url="https://idp/.well-known"))
    with patch("core.views.sso.requests.get") as get:
      get.return_value.json.return_value = dict()
      resp = self.client.get("/auth/sso/login/OIDC/", dict(org=org.id))
    self.assertEqual(error_of(resp), (500, "Could not determine authorization endpoint"))

  def test_oidc_redirect_merges_into_the_endpoint_query(self):
    org = make_org("OIDC", dict(client_id="cid", discovery_url="https://idp/.well-known"))
    with patch("core.views.sso.requests.get") as get:
      get.return_value.json.return_value = dict(authorization_endpoint="https://idp/auth?tenant=t")
      resp = self.client.get("/auth/sso/login/OIDC/", dict(org=org.id))
    get.assert_called_once_with("https://idp/.well-known", timeout=5)
    redirect = urllib.parse.quote(f"https://testserver/auth/sso/callback/OIDC/?org={org.id}", safe="")
    self.assertEqual(resp["Location"], (
      f"https://idp/auth?tenant=t&client_id=cid&response_type=code&redirect_uri={redirect}"
      f"&scope=openid+email+profile&state={self._state_of(resp)}"))


class CASCallbackFlowTests(APITestCase):

  def setUp(self):
    self.org = make_org("CAS", dict(cas_server_url="https://cas.idp.edu/cas/login"))

  def _configure(self, **config):
    self.org.sso_config = dict(cas_server_url="https://cas.idp.edu/cas/login", **config)
    self.org.save()

  def _callback(self, body=None, *, response=None, side_effect=None, params=None, seed=True):
    if seed:
      login_state(self.client)
    query = dict(org=self.org.id, ticket="ST-1", state="s1")
    query.update(params or dict())
    query = dict((k, v) for k, v in query.items() if v is not None)
    idp = response or MagicMock(status_code=200, content=body, text=(body or b"").decode())
    with patch("core.views.sso.requests.get", return_value=idp, side_effect=side_effect) as get:
      resp = self.client.get("/auth/sso/callback/CAS/", query)
    return resp, get

  def _service(self):
    return f"https://testserver/auth/sso/callback/CAS/?org={self.org.id}&state=s1"

  def _logged_in(self, resp):
    return resp["Location"].startswith(f"{settings.CLIENT_URL}/?token=")

  def test_v3_validation_request_is_exact(self):
    resp, get = self._callback(cas_ok("someone@idp.edu"))
    self.assertTrue(self._logged_in(resp))
    self.assertEqual(get.call_args_list, [call(
      "https://cas.idp.edu/cas/p3/serviceValidate",
      params=dict(service=self._service(), ticket="ST-1"), timeout=10, verify=True)])

  def test_v2_validates_at_service_validate(self):
    self._configure(cas_version=2)
    _, get = self._callback(cas_ok())
    self.assertEqual(get.call_args.args, ("https://cas.idp.edu/cas/serviceValidate",))

  def test_unknown_version_validates_at_service_validate(self):
    self._configure(cas_version="9")
    _, get = self._callback(cas_ok())
    self.assertEqual(get.call_args.args, ("https://cas.idp.edu/cas/serviceValidate",))

  def _v1(self, body):
    self._configure(cas_version="1")
    return self._callback(body)

  def test_v1_reads_the_username_from_the_second_line(self):
    resp, get = self._v1(b"yes\nnetid\n")
    self.assertTrue(self._logged_in(resp))
    self.assertEqual(get.call_args.args, ("https://cas.idp.edu/cas/validate",))
    self.assertTrue(User.objects.filter(email="netid@idp.edu").exists())

  def test_v1_refusal_cannot_extract_identity(self):
    resp, _ = self._v1(b"no\n")
    self.assertEqual(resp["Location"], err(NO_IDENTITY))

  def test_v1_truncated_body_answers_the_generic_failure(self):
    resp, _ = self._v1(b"yes")
    self.assertEqual(resp["Location"], err(GENERIC))

  def test_login_suffix_is_stripped_with_or_without_a_trailing_slash(self):
    for url in ("https://cas.idp.edu/cas/login/", "https://cas.idp.edu/cas"):
      self.org.sso_config = dict(cas_server_url=url)
      self.org.save()
      _, get = self._callback(cas_ok())
      self.assertEqual(get.call_args.args, ("https://cas.idp.edu/cas/p3/serviceValidate",))

  def test_non_200_from_cas(self):
    resp, _ = self._callback(response=MagicMock(status_code=503, text="down"))
    self.assertEqual(resp["Location"], err("Failed to contact CAS server"))

  def test_malformed_xml(self):
    resp, _ = self._callback(b"<not xml")
    self.assertEqual(resp["Location"], err("Invalid XML from CAS server"))

  def test_authentication_failure(self):
    failed = err("SSO authentication failed. Please try again or contact support.")
    resp, _ = self._callback(cas_xml("<cas:authenticationFailure code='INVALID_TICKET'>no</cas:authenticationFailure>"))
    self.assertEqual(resp["Location"], failed)
    resp, _ = self._callback(cas_xml("<cas:authenticationFailure/>"))
    self.assertEqual(resp["Location"], failed)

  def test_success_without_a_user_element(self):
    resp, _ = self._callback(cas_xml("<cas:authenticationSuccess/>"))
    self.assertEqual(resp["Location"], err(NO_IDENTITY))

  def test_bare_user_tag_fallback(self):
    resp, _ = self._callback(b"<serviceResponse><wrap><user>bare</user></wrap></serviceResponse>")
    self.assertTrue(self._logged_in(resp))
    self.assertTrue(User.objects.filter(email="bare@idp.edu").exists())

  def test_response_without_any_user_cannot_extract_identity(self):
    resp, _ = self._callback(b"<serviceResponse><other/></serviceResponse>")
    self.assertEqual(resp["Location"], err(NO_IDENTITY))

  def test_request_exception_answers_the_generic_failure(self):
    resp, _ = self._callback(side_effect=RuntimeError("boom"))
    self.assertEqual(resp["Location"], err(GENERIC))

  def test_non_string_server_url_answers_the_generic_failure(self):
    # A misconfigured (non-string) cas_server_url used to escape as a 500; since the
    # split the validation URL is built inside the guarded CAS call.
    self.org.sso_config = dict(cas_server_url=123)
    self.org.save()
    resp, get = self._callback(cas_ok())
    self.assertEqual(resp["Location"], err(GENERIC))
    get.assert_not_called()

  def test_missing_ticket_is_refused_before_the_state_is_claimed(self):
    resp, get = self._callback(cas_ok(), params=dict(ticket=None))
    self.assertEqual(resp["Location"], err("No ticket provided"))
    get.assert_not_called()
    self.assertTrue(self.client.session["sso_state:s1"])

  def test_state_errors_are_refused_before_the_ticket_is_spent(self):
    resp, get = self._callback(cas_ok(), params=dict(state=None))
    self.assertEqual(resp["Location"], err("Missing state parameter"))
    resp, get = self._callback(cas_ok(), params=dict(state="other"))
    self.assertEqual(resp["Location"], err("State parameter was not issued to this browser"))
    get.assert_not_called()

  def test_missing_server_url_consumes_the_state(self):
    self.org.sso_config = dict()
    self.org.save()
    resp, get = self._callback(cas_ok())
    self.assertEqual(resp["Location"], err("CAS Server URL missing"))
    get.assert_not_called()
    self.assertNotIn("sso_state:s1", self.client.session)

  def test_missing_and_unknown_organizations(self):
    resp, _ = self._callback(cas_ok(), params=dict(org=""))
    self.assertEqual(resp["Location"], err("Organization ID missing from callback"))
    for bad in ("abc", "999999"):
      resp, _ = self._callback(cas_ok(), params=dict(org=bad))
      self.assertEqual(resp["Location"], err("Organization not found"))

  def test_gate_messages(self):
    self.org.sso_enabled = False
    self.org.save()
    resp, _ = self._callback(cas_ok())
    self.assertEqual(resp["Location"], err("SSO is not enabled for this organization"))
    self.org.sso_enabled = True
    self.org.sso_provider = "AZURE"
    self.org.save()
    resp, _ = self._callback(cas_ok())
    self.assertEqual(resp["Location"], err("Organization is configured for AZURE, not CAS"))

  def test_unsupported_provider(self):
    org = make_org("LDAP", dict(), shortname="ldap", email_domain="ldap.edu")
    resp = self.client.get("/auth/sso/callback/LDAP/", dict(org=org.id))
    self.assertEqual(resp["Location"], err("Provider LDAP not supported yet in callback"))

  def test_netid_gets_the_org_domain_and_a_full_email_is_kept(self):
    self._callback(cas_ok("netid"))
    self._callback(cas_ok("full@other.edu"))
    self.assertTrue(User.objects.filter(email="netid@idp.edu").exists())
    self.assertTrue(User.objects.filter(email="full@other.edu").exists())

  def test_netid_without_an_org_domain_fails_to_resolve_a_user(self):
    self.org.email_domain = ""
    self.org.save()
    resp, _ = self._callback(cas_ok("netid"))
    self.assertEqual(resp["Location"], err("Failed to create/retrieve user locally"))

  def test_next_finishes_with_a_session_and_rides_the_service_url_raw(self):
    resp, get = self._callback(cas_ok("n@idp.edu"), params=dict(next=NEXT))
    self.assertEqual(resp["Location"], NEXT)
    self.assertIn("_auth_user_id", self.client.session)
    self.assertEqual(self.client.session.get_expiry_age(), 900)
    service = self._service().replace("&state=s1", f"&next={urllib.parse.quote(NEXT, safe='')}&state=s1")
    self.assertEqual(get.call_args.kwargs["params"]["service"], service)

  def test_invalid_next_still_rides_the_service_url_but_logs_in_normally(self):
    evil = "https://evil.test/o/authorize"
    resp, get = self._callback(cas_ok("n@idp.edu"), params=dict(next=evil))
    self.assertTrue(self._logged_in(resp))
    self.assertIn(f"&next={urllib.parse.quote(evil, safe='')}&state=s1", get.call_args.kwargs["params"]["service"])

  @override_settings(DEBUG=True)
  def test_service_url_uses_the_request_scheme_when_debugging(self):
    _, get = self._callback(cas_ok())
    self.assertEqual(get.call_args.kwargs["params"]["service"], self._service().replace("https", "http", 1))


def idp_json(payload, status=200):
  return MagicMock(status_code=status, json=lambda: payload, text="body")


class OAuthCallbackFlowTests(APITestCase):

  def _setup(self, provider, config=None, **fields):
    self.provider = provider
    self.org = make_org(provider, config or dict(client_id="cid", client_secret="sec"), **fields)
    return self.org

  def _prime(self, state="s1", cached=None):
    login_state(self.client, state)
    value = cached if cached is not None else json.dumps(dict(org=str(self.org.id), next=None))
    cache.set(f"sso_state:{state}", value, timeout=600)

  def _callback(self, *, token=None, get=None, params=None, post_side_effect=None):
    query = dict(org=self.org.id, code="c", state="s1")
    query.update(params or dict())
    query = dict((k, v) for k, v in query.items() if v is not None)
    token = token if token is not None else idp_json(dict(access_token="at"))
    with patch("core.views.sso.requests.post", return_value=token, side_effect=post_side_effect) as post, \
         patch("core.views.sso.requests.get", side_effect=get) as getter:
      resp = self.client.get(f"/auth/sso/callback/{self.provider}/", query)
    return resp, post, getter

  def _logged_in(self, resp):
    return resp["Location"].startswith(f"{settings.CLIENT_URL}/?token=")

  def _mail(self, address="m@idp.edu"):
    return lambda *a, **k: idp_json(dict(mail=address))

  def test_missing_and_unissued_state(self):
    self._setup("AZURE")
    resp, _, _ = self._callback(params=dict(state=None))
    self.assertEqual(resp["Location"], err("Missing state parameter"))
    resp, _, _ = self._callback(params=dict(state="zz"))
    self.assertEqual(resp["Location"], err("State parameter was not issued to this browser"))

  def test_state_unknown_to_the_cache_is_expired(self):
    self._setup("AZURE")
    login_state(self.client)
    cache.delete("sso_state:s1")
    resp, post, _ = self._callback()
    self.assertEqual(resp["Location"], err("Invalid or expired state parameter"))
    post.assert_not_called()

  def test_state_is_deleted_from_the_cache_on_use(self):
    self._setup("AZURE")
    self._prime()
    self._callback(get=self._mail())
    self.assertIsNone(cache.get("sso_state:s1"))

  def test_state_for_another_organization_is_refused(self):
    self._setup("AZURE")
    self._prime(cached=json.dumps(dict(org="999999", next=None)))
    resp, post, _ = self._callback()
    self.assertEqual(resp["Location"], err("State parameter does not match organization"))
    post.assert_not_called()

  def test_legacy_plain_string_state_is_honoured_even_when_numeric(self):
    self._setup("AZURE")
    self._prime(cached=str(self.org.id))
    resp, _, _ = self._callback(get=self._mail())
    self.assertTrue(self._logged_in(resp))

  def test_legacy_non_json_state_is_compared_as_text(self):
    self._setup("AZURE")
    self._prime(cached="not-json")
    resp, _, _ = self._callback()
    self.assertEqual(resp["Location"], err("State parameter does not match organization"))

  def test_missing_code(self):
    self._setup("AZURE")
    self._prime()
    resp, post, _ = self._callback(params=dict(code=None))
    self.assertEqual(resp["Location"], err("No auth code provided"))
    post.assert_not_called()

  def test_azure_exchange_and_graph_calls_are_exact(self):
    self._setup("AZURE", dict(client_id="cid", client_secret="sec", tenant_id="tnt"))
    self._prime()
    resp, post, getter = self._callback(get=lambda *a, **k: idp_json(dict(userPrincipalName="upn@idp.edu")))
    self.assertTrue(self._logged_in(resp))
    self.assertTrue(User.objects.filter(email="upn@idp.edu").exists())
    post.assert_called_once_with(
      "https://login.microsoftonline.com/tnt/oauth2/v2.0/token",
      data=dict(client_id="cid", client_secret="sec", code="c", grant_type="authorization_code",
                redirect_uri=f"https://testserver/auth/sso/callback/AZURE/?org={self.org.id}"),
      timeout=10)
    self.assertEqual(getter.call_args_list, [call(
      "https://graph.microsoft.com/v1.0/me", headers=dict(Authorization="Bearer at"), timeout=10)])

  def test_google_calls_are_exact_and_userinfo_failure_falls_back_to_the_id_token(self):
    self._setup("GOOGLE")
    self._prime()
    token = idp_json(dict(access_token="at", id_token=jwt_with(dict(email="claim@idp.edu"))))
    resp, post, getter = self._callback(token=token, get=lambda *a, **k: idp_json(dict(), status=401))
    self.assertTrue(self._logged_in(resp))
    self.assertTrue(User.objects.filter(email="claim@idp.edu").exists())
    self.assertEqual(post.call_args.args, ("https://oauth2.googleapis.com/token",))
    self.assertEqual(getter.call_args_list, [call(
      "https://www.googleapis.com/oauth2/v3/userinfo", headers=dict(Authorization="Bearer at"), timeout=10)])

  def test_id_token_preferred_username_and_garbage(self):
    self._setup("GOOGLE")
    for id_token, ok in ((jwt_with(dict(preferred_username="pu@idp.edu")), True),
                         ("garbage", False), ("h.%%%.s", False)):
      self._prime()
      token = idp_json(dict(access_token="at", id_token=id_token))
      resp, _, _ = self._callback(token=token, get=lambda *a, **k: idp_json(dict(), status=500))
      if ok:
        self.assertTrue(self._logged_in(resp))
      else:
        self.assertEqual(resp["Location"], err(NO_IDENTITY))

  def test_token_exchange_non_200(self):
    self._setup("GOOGLE")
    self._prime()
    resp, _, getter = self._callback(token=idp_json(dict(), status=400))
    self.assertEqual(resp["Location"], err("Failed to exchange code for token"))
    getter.assert_not_called()

  def test_token_exchange_failure_answers_the_generic_error(self):
    self._setup("GOOGLE")
    self._prime()
    resp, _, _ = self._callback(post_side_effect=RuntimeError("boom"))
    self.assertEqual(resp["Location"], err(GENERIC))

  def test_no_email_anywhere(self):
    self._setup("AZURE")
    self._prime()
    resp, _, _ = self._callback(get=lambda *a, **k: idp_json(dict()))
    self.assertEqual(resp["Location"], err(NO_IDENTITY))

  def _oidc(self, config=None):
    self._setup("OIDC", config or dict(client_id="cid", client_secret="sec", discovery_url="https://idp/.wk"))
    self._prime()

  def test_oidc_without_discovery_url(self):
    self._oidc(dict(client_id="cid"))
    resp, _, getter = self._callback()
    self.assertEqual(resp["Location"], err("Discovery URL missing"))
    getter.assert_not_called()

  def test_oidc_discovery_failure(self):
    self._oidc()
    resp, post, _ = self._callback(get=RuntimeError("boom"))
    self.assertEqual(resp["Location"], err("OIDC discovery failed in callback"))
    post.assert_not_called()

  def test_oidc_without_a_token_endpoint(self):
    self._oidc()
    resp, post, _ = self._callback(get=lambda *a, **k: idp_json(dict(userinfo_endpoint="https://idp/ui")))
    self.assertEqual(resp["Location"], err("Token endpoint not found"))
    post.assert_not_called()

  def test_oidc_reads_the_userinfo_endpoint(self):
    self._oidc()
    answers = dict([
      ("https://idp/.wk", idp_json(dict(token_endpoint="https://idp/tok", userinfo_endpoint="https://idp/ui"))),
      ("https://idp/ui", idp_json(dict(email="oidc@idp.edu"))),
    ])
    resp, post, getter = self._callback(get=lambda url, **k: answers[url])
    self.assertTrue(self._logged_in(resp))
    self.assertEqual(post.call_args.args, ("https://idp/tok",))
    self.assertEqual(getter.call_args_list, [
      call("https://idp/.wk", timeout=5),
      call("https://idp/ui", headers=dict(Authorization="Bearer at"), timeout=10)])

  def test_oidc_without_userinfo_endpoint_uses_the_id_token(self):
    self._oidc()
    token = idp_json(dict(access_token="at", id_token=jwt_with(dict(email="idt@idp.edu"))))
    resp, _, getter = self._callback(token=token, get=lambda *a, **k: idp_json(dict(token_endpoint="https://idp/tok")))
    self.assertTrue(self._logged_in(resp))
    self.assertEqual(getter.call_count, 1)

  def test_next_from_the_cached_state_finishes_with_a_session(self):
    self._setup("AZURE")
    self._prime(cached=json.dumps(dict(org=str(self.org.id), next=NEXT)))
    resp, _, _ = self._callback(get=self._mail("n@idp.edu"))
    self.assertEqual(resp["Location"], NEXT)
    self.assertIn("_auth_user_id", self.client.session)

  def test_invalid_cached_next_falls_back_to_the_spa_redirect(self):
    self._setup("AZURE")
    self._prime(cached=json.dumps(dict(org=str(self.org.id), next="https://evil.test/o/authorize")))
    resp, _, _ = self._callback(get=self._mail("n@idp.edu"))
    self.assertTrue(self._logged_in(resp))
    self.assertNotIn("_auth_user_id", self.client.session)
