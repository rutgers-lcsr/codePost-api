# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""sso_callback must apply the same org gates as initiate_sso: the org must have SSO
enabled and be configured for the provider named in the callback URL. Only the HTTP
call to the IdP is mocked; organizations and users are real rows."""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import Organization

CAS_OK = b"""<cas:serviceResponse xmlns:cas='http://www.yale.edu/tp/cas'>
    <cas:authenticationSuccess><cas:user>victim@vic.edu</cas:user></cas:authenticationSuccess>
</cas:serviceResponse>"""


class SSOCallbackGatingTests(APITestCase):

    def setUp(self):
        self.victim = User.objects.create(username="victim@vic.edu", email="victim@vic.edu", is_active=True)

    def _org(self, **overrides):
        fields = dict(
            name="Attacker Org", shortname="attack", email_domain="attack.edu",
            sso_enabled=True, sso_provider="CAS", sso_config={"cas_server_url": "https://cas.attack.edu"},
        )
        fields.update(overrides)
        return Organization.objects.create(**fields)

    def _callback(self, org, provider="CAS"):
        # A login this browser started, so only the org gates can refuse it.
        session = self.client.session
        session["sso_state:s1"] = True
        session.save()
        idp = MagicMock(status_code=200, content=CAS_OK)
        with patch("core.views.sso.requests.get", return_value=idp):
            return self.client.get(f"/auth/sso/callback/{provider}/",
                                   {"org": org.id, "ticket": "ST-1", "state": "s1"})

    def test_enabled_matching_org_logs_in(self):
        resp = self._callback(self._org())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("token=", resp["Location"])

    def test_disabled_org_is_rejected(self):
        resp = self._callback(self._org(sso_enabled=False))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=", resp["Location"])
        self.assertNotIn("token=", resp["Location"])

    def test_provider_mismatch_is_rejected(self):
        # Org is configured for AZURE but its leftover config also names a CAS server;
        # a callback arriving on the CAS route must not be honoured.
        org = self._org(sso_provider="AZURE", sso_config={"cas_server_url": "https://cas.attack.edu"})
        resp = self._callback(org, provider="CAS")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=", resp["Location"])
        self.assertNotIn("token=", resp["Location"])
