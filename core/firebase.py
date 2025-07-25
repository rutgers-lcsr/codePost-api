from django.contrib.auth.models import User
from django.utils.encoding import force_str
from rest_framework import authentication
from rest_framework import exceptions
from django.utils.translation import ugettext as _
from util.slack import Slack

#################################################################################
# Adapted with immense grattitude from:
# https://github.com/wesleylima/django-rest-framework-firebase/blob/master/rest_framework_firebase/authentication.py
#################################################################################

#################################################################################
# CODEPOST CONFIG
#################################################################################
FIREBASE_AUTH_HEADER_PREFIX = "Firebase"
# FIREBASE_UID_FIELD = 'username' # where we store the user's UID

#################################################################################
# FIREBASE CONFIG
# Using code-in-place-test app
# FIXME: switch to service account for Code in Place's production Firebase app
# Note that if we want to transition codePost auth to Firebase, we will need
# to transition this authentication class away from Code in Place and to our own
# app. Or, create a second authentication class that runs our firebase_admin
# app in parallel.
#################################################################################

# Test local
# FIREBASE_CONFIG = {
#     "type": "service_account",
#     "project_id": "code-in-place-test",
#     "private_key_id": "43233d0ce34baef38ea9a8fd56b8db004816d999",
#     "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC0CFNgjitnGjVw\nm8jvEAANbJicE9ip4Yhg2e3JHFELVNgMDAypLM8JkjwG1qUX4vhvFo8xKo6V7q8W\n8Teq2zD4+uZWdraI87rtbFhmQrvJV33miY/Q7v85kTmKztU+eIINA8tI11agBe1g\nCIY6NWWgiJuXjE0hzKrvl07ctQysfOyeVzxVrJnAbITtmlmYu6YS7YBgN1muKHbh\nKuNePEnhfT/H3KgNh+Lya+cA+Y5lxCBWo5FgF3pilLzGj2MX+S5/IhU+xiblgOnk\nT6NvSLJHCklEUP9pjibZJzzFPqkQmATIBYcaI0AOXxCGYNS7BH1h4d32tA4OxPAp\niBEx8WLHAgMBAAECggEAFDtBShRVT/tT2RPwrd428KCXunvHzo4lRM5eGJ/MLcFQ\nRsj4h+8cqcnbYWCwDIdO/YY5UOr5kLjSHU+96T9DpB88plJ7QIMJ/9IRUcCbGM0d\nEry6bYjbeVfWxxYSRGMc06NDA4G2NDp7oAilM5e6Ps2glT8eOzekV/4WzdpcvRSw\nlDAJ9lS8beX/+TLgK2U/R61At2BsH7CwABoWbp3oFwHH8lODLMz1VH9CmNg5eIo3\nbqOvERTzUsoh3oQ+nMhPGw5PVnQ3+5aWLMvbuCwBNuvyB/HrtA+Zw2DfZRQFqMil\ndXUnsHvVHBShaKHeFd9fTRvNod2G4juEpQbK1cufZQKBgQD+HeR01iVybCp+ofPt\nl7zLoGpEuznYW2QjikwsgWwe8QZS+MatnrMr+tHwD3uku4u5aUetjbVkWtYKH95+\ngmNbyVgx52QP5cO1DXiIhsrRH/hCw4pa7V+fzNoH3kWClR2Yit0P6L58ECctKRwt\nWnSw5yQY+PUR3ACnx/ClzkPWvQKBgQC1XeGm6NrSrbhwMKiX2YdX1BgCMZPBGoVC\nRhhnHFeekhuZ4r/uLM5Ng2tlE3hOMspwwfOXglG2Mep18CDvw7JjT0jzSXLFXFqn\nPNvrNf4Q4V8Z37NnU21K3LplHx506bbKyCoNu5STDeXxPGYkoasSxqcsTZD7xyje\nx4nPX3HJ0wKBgQDyXjpmgVUoBCinrPoFc4L7SB3zPgtW4xvoleA/VpV0EXhxrJt6\nPvIvEUQozeuk28fRaKuXyZ/nfofFEk5YpS30/l3jAwo563A1AAslVEKfIPndW7lb\nLinVNUIC3Sm4+VZIBrH/mYIMvC9RcHNSgoLnsx2Hv/OmPApX/Gf3DHtBlQKBgQCm\no36sM/CyeAkpk5ukAar4CJiSk2i1mR9tWCgdvQ3IVWhkyNEeDi7zS1eGhBAakVIt\nrhaZU5SuOUi6Wgp5Ia6qznMxjX+VVJi6ZhGOGIq6icguZrpYqm+VxB7CwIfkVcSs\npqL1AS+uuatXLe6Po7ciRkHdU9ttanzjzCST05ciHwKBgHneqlRkHpfY+NYBqgKU\ndsaCS87bhL5qUcXKKhM2HKBajd70QrIlxFfnSN0VJK6V27i7mpUKKgGkVpFXHF4w\ngM2EBM9ufgROGcaNnn0KkYIzzWZ77+H1RGEEFYdpkq07dp7hz6XWw+5h1SB6XJj0\n/yxpCjr9D5yzcg8G/BQsI5ES\n-----END PRIVATE KEY-----\n",
#     "client_email": "firebase-adminsdk-wiqg8@code-in-place-test.iam.gserviceaccount.com",
#     "client_id": "101458129133385962094",
#     "auth_uri": "https://accounts.google.com/o/oauth2/auth",
#     "token_uri": "https://oauth2.googleapis.com/token",
#     "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
#     "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-wiqg8%40code-in-place-test.iam.gserviceaccount.com"
# }
FIREBASE_CONFIG = {
    "type": "service_account",
    "project_id": "cs106a-open",
    "private_key_id": "f6fa0d6b2d6934c34d23cce211a6b7fd6842efb5",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCJZhWoykzwkuIY\nU92YIiALJXcwZe9iKd60Rf8ugF7yAqmySzgZY029ck/vkNV2OZCEJi6HkfeBa/cZ\nLRGfGp+R36TPPQejwtRvwR8IdLjEpFkSIEZqHkKn+GWXA6j4L2A1N0YdhyZqZavB\nWn1tJs1pWijsaNJAPW7vPjGNagDKzF6L9mMl+KNGHYWUvhVvSFhVKvoYzE1pgKHw\nopZ8fWPDFifJN0MlkSpLx082iUbv7ad6ZKkoevPZzFudXgQZiM2vDmbfzrGEQP6l\nZz0EzCKU/KOXX6L9rexRxaLau/Kvx2KjOT17AJ77KKjPkH1j9rEAmai1Ctogz9p2\njfR12QKxAgMBAAECggEAFlxejIaF8IYbFTX645I0MFQz2lTQmWNyiti0b7M1IIJF\n704WDm2unnUO5NBnqRKzvgn/uxEKnI2/XGHNEx1wWDtzNUX7qw9fZuOhYw0p79jG\nZTCK/SS5GOCQWfwewOtm5yo8dzxCSIEM644ISR4OQoXJkLX7d7h3yChRRLA6ekZ8\n0T4kJ6kotFA9ZnjEIJYKeSnk95AjYM9aqq1SkToWm0hOh62KOLaAhnIinoWcg8ZJ\nJX4PIf+yrzjd77J0/AHXuOXlE0A+30ang635KKuudi2Ig/HCV68+IdTdwoJNZXmc\nDKyqW3IZMcz3QkbOj3hwS0mp3xeyB3Xx9NpkpBRTpQKBgQDAO7bSZQIQxb8vOz3m\nAAjGRm0H35vHi1uZHrjMYtfDvEUz70SU0UQDwxHVjpUMd13GggrScspL/nM9TsAZ\n58bGgTsh6sfCYI4iU37JdAqett99N1PsDkzZQ4SXzVEAdo5ngW1ZkamIvMh76imf\nrbd8b6KS2nLFiS4T5wgSpVB1vQKBgQC2+d8zGjs3JO2Qge2ezTr5A/lm89O58o2H\nKoRhgQav/C91i//lgo3RgICY3Gk2rOQtCbk2wjL+lxdNCZ6WqXv/G8jv5v8Fwsih\nKKqxJrsLGskDFKeZ4cYjt6L8xjCtbU0Iu/+gPzuNm7veKdwxKppYyTP5ixXrmuQN\npchR56XuBQKBgAQ7jFv3k2MRJ5N/p25AA/FxrYbl2oU7QUoOzhzZ9ExAAfoRw53P\nOcMncWYVXJzIqAzt4hUeJ+wibyEjccFgRBUs1UN66ukRvS9uTTVcU7uI5UTZigSB\nkBmcjffVsnnjImGPDPxS47u6BGQOFNqKNacMwjSfkLVevt/7T0cx0qK1AoGBAI00\nqBs30xrrVKqAmnBC0Y/6kS3yXSLTHIWDOkZE3HRTmgyMzh7AcdGL6bIN5uRa6HwZ\nVOX9WH1A/KpnEgwTH63wM1FwYr5/Y3V7fL7ZtN8M/LNz7SPEKLTHsvB/wnEUOK7U\n5qE0KzFNTd5VT6hhyFtcas/ZlkEMd5JQrhcHPfZBAoGAGd+BIeaIixe0kfMM/2Ow\n2s1ekCAV78Bbkdw6i/ELyFqjUmgLdrfSQCiD9mvaIXc/sjV3xuJjprqNunwTL+LL\nL8TG9xwr9cWsgydKdHDNWQrYXbpfXBGThCR1ugzVuVZ1n9xSym5EgTDizKP60VLS\nLRMIJRc5waSJ6OsXJc1giSo=\n-----END PRIVATE KEY-----\n",
    "client_email": "codepost-223@cs106a-open.iam.gserviceaccount.com",
    "client_id": "118043581858724957742",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/codepost-223%40cs106a-open.iam.gserviceaccount.com"
}


# firebase = initialize_app(credentials.Certificate(FIREBASE_CONFIG))

#################################################################################


class BaseFirebaseAuthentication(authentication.BaseAuthentication):
    """
    Token based authentication using firebase.
    """

    def _authenticate_credentials(self, payload):
        """
        Returns an active user that matches the payload's user uid.
        """
        # uid_field = FIREBASE_UID_FIELD
        uid = payload['uid']
        user = None

        if not uid:
            msg = _('Invalid payload.')
            raise exceptions.AuthenticationFailed(msg)

        try:
            if not payload.get('email', None):
                msg = _('Unknown auth method')
                raise exceptions.AuthenticationFailed(msg)

            user = User.objects.get(email=payload.get('email'))

        except User.DoesNotExist:
            msg = _('User does not exist')
            raise exceptions.AuthenticationFailed(msg)

            # FIXME: At this point, we have a valid Firebase token for a user that doesn't exist in the codePost data
            # We could choose to create this user and add them to the Code in Place course
            #
            # This is probably the right thing to do to accommodate new users
            # For now, let's log a Slack message
    
        if not user.is_active:
            msg = _('User account is disabled.')
            raise exceptions.AuthenticationFailed(msg)

        return user

    def get_token(self, request):
        auth = authentication.get_authorization_header(request).split()
        auth_header_prefix = FIREBASE_AUTH_HEADER_PREFIX.lower()

        if not auth:
            return None

        if len(auth) == 1:
            msg = _('Invalid Authorization header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = _('Invalid Authorization header. Credentials string '
                    'should not contain spaces.')
            raise exceptions.AuthenticationFailed(msg)

        if force_str(auth[0].lower()) != auth_header_prefix:
            return None

        return auth[1]

    def authenticate(self, request):
        """
        Returns a two-tuple of `User` and token if a valid signature has been
        supplied using Firebase authentication.  Otherwise returns `None`.
        """
        firebase_token = self.get_token(request)
        if firebase_token is None:
            return None

        try:
            payload = auth.verify_id_token(firebase_token)
        except Exception as e:
            msg = _('Could not log in.')
            raise exceptions.AuthenticationFailed(msg)

        user = self._authenticate_credentials(payload)

        return (user, payload)
