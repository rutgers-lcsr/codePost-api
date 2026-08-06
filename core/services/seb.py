# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Safe Exam Browser (SEB) request verification.

SEB stamps every HTTP request with an ``X-SafeExamBrowser-ConfigKeyHash`` header:
SHA256(absolute request URL + Config Key), Base16-encoded. The Config Key is shown
in the SEB Config Tool and pasted onto the quiz by the instructor (Quiz.sebConfigKey).
See https://safeexambrowser.org/developer/seb-config-key.html.

The absolute URL SEB hashed is the external one, so we hash two candidates: the URL
Django reconstructs from the request (correct behind the standard nginx deployment,
which forwards Host + X-Forwarded-Proto) and API_URL + path as a fallback for
multi-host setups.
"""
import hashlib
import json
import logging
import plistlib
from urllib.parse import quote, urlencode, urljoin

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

SEB_CONFIG_KEY_HEADER = 'HTTP_X_SAFEEXAMBROWSER_CONFIGKEYHASH'

REASON_MISSING_HEADER = 'missing_header'
REASON_INVALID_KEY = 'invalid_key'
REASON_NOT_CONFIGURED = 'not_configured'

# Matches JavaScript's encodeURIComponent, which the SPA uses to build course URLs.
_ENCODE_URI_COMPONENT_SAFE = "!'()*-._~"


def seb_permission_denied(reason):
  """A PermissionDenied whose body mirrors the accessCode 403 pattern.

  The detail dict is assigned after construction: __init__ would coerce every value
  to an ErrorDetail string, turning the lockdownRequired boolean into "True" on the
  wire. Assigning post-init keeps the raw dict, which DRF's exception handler renders
  verbatim."""
  exc = PermissionDenied()
  exc.detail = {  # type: ignore[assignment]
      'detail': 'This quiz must be taken in Safe Exam Browser.',
      'lockdownRequired': True,
      'lockdownReason': reason,
  }
  return exc


def is_exempt(user, quiz):
  """Whether the student holds a sebExempt accommodation in the quiz's course."""
  from core.models import QuizAccommodation
  return QuizAccommodation.objects.filter(
      course=quiz.course, student=user, sebExempt=True).exists()


def _candidate_keys(user, quiz):
  """The Config Keys a request may verify against: the instructor's pasted key plus
  the student's unexpired one-click-launch keys."""
  from core.models import QuizSebLaunch
  keys = []
  if quiz.sebConfigKey:
    keys.append(quiz.sebConfigKey.strip().lower())
  keys.extend(
      k.lower() for k in QuizSebLaunch.objects.filter(
          quiz=quiz, student=user, expiresAt__gt=timezone.now(),
      ).values_list('configKey', flat=True))
  return keys


def verify_seb_request(request, quiz):
  """Verify a request against a SEB-required quiz's Config Keys.

  Returns None when the request verifies (or the student is SEB-exempt), or a
  denial reason string (REASON_* constant) when it must be blocked.
  """
  if is_exempt(request.user, quiz):
    return None
  header = request.META.get(SEB_CONFIG_KEY_HEADER, '').strip()
  if not header:
    return REASON_MISSING_HEADER
  keys = _candidate_keys(request.user, quiz)
  if not keys:
    return REASON_NOT_CONFIGURED

  urls = (
      request.build_absolute_uri(),
      urljoin(settings.API_URL, request.get_full_path()),
  )
  for key in keys:
    for url in urls:
      expected = hashlib.sha256((url + key).encode('utf-8')).hexdigest()
      if expected == header.lower():
        return None
  logger.debug('SEB hash mismatch for quiz %s; candidate URLs: %s', quiz.pk, urls)
  return REASON_INVALID_KEY


# ---------------------------------------------------------------------------
# One-click launch: server-generated .seb config + Config Key
#
# SEB computes the Config Key from the config file it loads (JSON-normalized per
# safeexambrowser.org/developer/seb-config-key.html); the server computes the same
# key at generation time, so per-request hashes verify without the instructor ever
# touching the SEB Config Tool. The normalization below (case-insensitively sorted
# keys, compact JSON) ports Sakai's field-proven SecureDeliverySeb implementation
# and is only ever applied to configs we generate ourselves.
# ---------------------------------------------------------------------------

def build_seb_config(start_url):
  """The SEB config dict for a launch: kiosk hardening + the tokenized start URL.

  Key set kept deliberately small and flat — the Config Key normalization is only
  guaranteed against configs of this shape.
  """
  return {
      'startURL': start_url,
      'quitURL': f"{settings.CLIENT_URL}/seb/quit",
      'allowQuit': True,
      'quitURLConfirm': True,
      'browserWindowAllowReload': False,
      'showReloadButton': False,
      'allowPreferencesWindow': False,
      'examSessionClearCookiesOnStart': False,
      'sebServiceIgnore': False,
      'browserWindowWebView': 3,
  }


def config_to_plist(config):
  """The config as SEB's on-disk format (XML plist), as text."""
  return plistlib.dumps(config, sort_keys=True).decode('utf-8')


def compute_config_key(config):
  """SHA256 of the config's normalized JSON form — what SEB derives from the same
  file and salts request-URL hashes with."""
  normalized = {k: config[k] for k in sorted(config, key=str.lower) if config[k] is not None}
  return hashlib.sha256(
      json.dumps(normalized, separators=(',', ':')).encode('utf-8')).hexdigest()


def quiz_take_path(quiz):
  """The SPA route where a student takes this quiz, encoded the way the SPA builds it."""
  name = quote(quiz.course.name, safe=_ENCODE_URI_COMPONENT_SAFE)
  period = quote(quiz.course.period, safe=_ENCODE_URI_COMPONENT_SAFE)
  return f"/student/{name}/{period}/quizzes/{quiz.pk}/take"


def build_launch_start_url(quiz, ott_token):
  """The generated config's startURL: the SPA's SEB-launch handoff route, carrying the
  one-time token (SEB starts a fresh session with no stored auth) and the take route."""
  query = urlencode({'ott': str(ott_token), 'redirect': quiz_take_path(quiz)})
  return f"{settings.CLIENT_URL}/seb/launch?{query}"
