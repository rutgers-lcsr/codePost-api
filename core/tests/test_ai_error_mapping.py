# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""AI provider failures: AIService._parse_error classification (by exception type and
status code, never by message text) and POST /promptVariants/auto-improve/ error mapping
(400 not configured, 502 provider failure, never the raw provider text)."""
from typing import cast
from unittest.mock import AsyncMock, patch

import factory
import httpx
import openai
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from google.genai import errors as genai_errors
from rest_framework.test import APITestCase

from core.models import Course, PromptFeedback, PromptLabSettings, SystemPromptVariant
from core.services.ai_service import AIService
from core.tests.factories import CourseFactory, SubmissionFileFactory
from core.tests.test_ai_service import _make_course


def _service(api_key='AIzaRealLookingKey'):
  course = _make_course(ai_use_own_settings=True, ai_provider='gemini', ai_api_key=api_key)
  return AIService(cast(Course, course))


def _openai_status_error(cls, status):
  request = httpx.Request('POST', 'https://api.openai.com/v1/chat/completions')
  response = httpx.Response(status, request=request)
  return cls('provider said something', response=response, body=None)


class ParseErrorTests(APITestCase):
  def test_status_code_429_is_quota_even_when_message_is_empty(self):
    msg = _service()._parse_error(genai_errors.ClientError(429, {'error': {'message': 'x'}}))
    self.assertIn('quota', msg.lower())

  def test_openai_rate_limit_error_is_quota(self):
    msg = _service()._parse_error(_openai_status_error(openai.RateLimitError, 429))
    self.assertIn('quota', msg.lower())

  def test_429_digits_in_a_plain_message_are_not_quota(self):
    msg = _service()._parse_error(Exception('Bad request: request id req-14290-x, schema mismatch'))
    self.assertNotIn('quota', msg.lower())

  def test_invalid_json_key_message_is_not_an_api_key_error(self):
    msg = _service()._parse_error(Exception('invalid JSON: missing key "questions"'))
    self.assertNotIn('Invalid API key', msg)

  def test_google_invalid_key_reason_is_api_key_error(self):
    err = genai_errors.ClientError(400, {'error': {
      'code': 400, 'status': 'INVALID_ARGUMENT', 'message': 'API key not valid.',
      'details': [{'@type': 'type.googleapis.com/google.rpc.ErrorInfo', 'reason': 'API_KEY_INVALID'}],
    }})
    self.assertIn('Invalid API key', _service()._parse_error(err))

  def test_google_invalid_key_with_undecryptable_stored_key_names_the_real_cause(self):
    err = genai_errors.ClientError(400, {'error': {
      'code': 400, 'message': 'API key not valid.',
      'details': [{'reason': 'API_KEY_INVALID'}],
    }})
    self.assertIn('FIELD_ENCRYPTION_KEY', _service('gAAAAABoffFake')._parse_error(err))

  def test_401_is_authentication_failure(self):
    msg = _service()._parse_error(_openai_status_error(openai.AuthenticationError, 401))
    self.assertIn('Authentication failed', msg)

  def test_connection_errors_are_connection_failures(self):
    svc = _service()
    for err in (
      openai.APIConnectionError(request=httpx.Request('POST', 'https://x.test')),
      httpx.ConnectError('boom'),
      httpx.ReadTimeout('slow'),
      TimeoutError('slow'),
    ):
      with self.subTest(err=type(err).__name__):
        self.assertIn('connect', svc._parse_error(err).lower())

  def test_404_is_model_not_found(self):
    msg = _service()._parse_error(genai_errors.ClientError(404, {'error': {'message': 'x'}}))
    self.assertIn('not found', msg)

  def test_google_400_with_another_reason_is_not_an_api_key_error(self):
    err = genai_errors.ClientError(400, {'error': {
      'code': 400, 'message': 'bad request',
      'details': [{'reason': 'SOMETHING_ELSE'}, {'reason': 'OTHER'}],
    }})
    self.assertNotIn('Invalid API key', _service()._parse_error(err))

  def test_google_invalid_key_reason_found_among_several_details(self):
    err = genai_errors.ClientError(400, {'error': {
      'code': 400, 'message': 'bad',
      'details': [{'reason': 'SOMETHING_ELSE'}, {'reason': 'API_KEY_INVALID'}],
    }})
    self.assertIn('Invalid API key', _service()._parse_error(err))

  def test_provider_5xx_is_unavailable(self):
    svc = _service()
    for code in (500, 503):
      with self.subTest(code=code):
        msg = svc._parse_error(genai_errors.ServerError(code, {'error': {'message': 'x'}}))
        self.assertIn('unavailable', msg.lower())

  def test_499_is_not_unavailable(self):
    msg = _service()._parse_error(genai_errors.ClientError(499, {'error': {'message': 'x'}}))
    self.assertNotIn('unavailable', msg.lower())

  def test_unclassified_error_never_echoes_raw_text(self):
    msg = _service()._parse_error(
      Exception('Internal failure at https://internal.host/v1 token=abc123 secret'))
    for leaked in ('internal.host', 'abc123', 'secret'):
      self.assertNotIn(leaked, msg)
    self.assertTrue(msg.startswith('AI generation failed'))


class AutoImproveErrorMappingTests(APITestCase):
  def setUp(self):
    self.su = get_user_model().objects.create_superuser('su@x.edu', 'su@x.edu', 'pw')
    self.client.force_authenticate(user=self.su)
    self.pt = SystemPromptVariant.PROMPT_TYPE_CHOICES[0][0]
    for _ in range(10):
      PromptFeedback.objects.create(
        prompt_type=self.pt, rating=1, feedback_text='x', ai_output_a='a', ai_output_b='b',
        is_custom_context=False)
    self.url = f'/promptVariants/auto-improve/?promptType={self.pt}'

  def _configure(self, provider):
    lab = PromptLabSettings.load()
    lab.ai_provider = provider
    lab.ai_api_key = 'k'
    lab.save()

  def test_provider_failure_is_502_without_raw_text(self):
    self._configure('gemini')
    with patch('core.services.prompt_improvement._call_gemini',
               side_effect=Exception('sk-SECRET-KEY-123 quota exceeded')):
      r = self.client.post(self.url)
    self.assertEqual(r.status_code, 502, r.content)
    self.assertIsInstance(r.json()['detail'], str)
    self.assertNotIn('SECRET', r.content.decode())

  def test_openai_provider_failure_is_502(self):
    self._configure('openai')
    with patch('core.services.prompt_improvement._call_openai',
               side_effect=Exception('boom')):
      r = self.client.post(self.url)
    self.assertEqual(r.status_code, 502, r.content)

  def test_empty_provider_response_is_502(self):
    self._configure('gemini')
    with patch('google.genai.Client') as client:
      client.return_value.models.generate_content.return_value.text = ''
      r = self.client.post(self.url)
    self.assertEqual(r.status_code, 502, r.content)

  def test_unconfigured_provider_is_400_with_reason(self):
    lab = PromptLabSettings.load()
    lab.ai_provider = ''
    lab.ai_api_key = ''
    lab.save()
    r = self.client.post(self.url)
    self.assertEqual(r.status_code, 400, r.content)
    self.assertIn('Prompt Lab', r.json()['detail'])

  def test_provider_without_api_key_is_400(self):
    lab = PromptLabSettings.load()
    lab.ai_provider = 'gemini'
    lab.ai_api_key = ''
    lab.save()
    self.assertEqual(self.client.post(self.url).status_code, 400)

  def test_api_key_without_provider_is_400(self):
    lab = PromptLabSettings.load()
    lab.ai_provider = ''
    lab.ai_api_key = 'k'
    lab.save()
    self.assertEqual(self.client.post(self.url).status_code, 400)

  def test_configured_model_is_used_else_provider_default(self):
    for provider, func, default in (('gemini', '_call_gemini', 'gemini-2.5-pro'),
                                    ('openai', '_call_openai', 'gpt-4o')):
      for model, expected in (('my-model', 'my-model'), ('', default)):
        lab = PromptLabSettings.load()
        lab.ai_provider = provider
        lab.ai_api_key = 'k'
        lab.ai_model = model
        lab.save()
        with self.subTest(provider=provider, model=model), patch(
            f'core.services.prompt_improvement.{func}', return_value='t') as call:
          self.client.post(self.url)
          self.assertEqual(call.call_args.args[:2], ('k', expected))

  def test_unsupported_provider_is_400(self):
    self._configure('mystery')
    r = self.client.post(self.url)
    self.assertEqual(r.status_code, 400, r.content)

  def test_success_creates_draft_variant(self):
    self._configure('gemini')
    with patch('core.services.prompt_improvement._call_gemini', return_value='better prompt'):
      r = self.client.post(self.url)
    self.assertEqual(r.status_code, 201, r.content)
    self.assertEqual(
      SystemPromptVariant.objects.get(prompt_type=self.pt, status='draft').text, 'better prompt')


class AssignmentAiEndpointProviderFailureTests(APITestCase):
  """A provider exception at the client boundary is a 502 (not a 500) on every AI endpoint."""

  def setUp(self):
    with factory.django.mute_signals(post_save):
      self.course = CourseFactory()
    self.course.ai_use_own_settings = True
    self.course.ai_provider = 'openai'
    self.course.ai_api_key = 'test-key'
    self.course.save()
    self.assignment = self.course.assignments.first()
    self.admin = self.course.courseAdmins.first()
    self.client.force_authenticate(user=self.admin)

  def _provider_down(self):
    return patch('core.services.ai_service.AIService._dispatch_provider',
                 new=AsyncMock(side_effect=ConnectionError('network down https://internal.host')))

  def test_generate_description_provider_exception_is_502(self):
    with self._provider_down():
      r = self.client.post(f'/assignments/{self.assignment.id}/generateDescription/')
    self.assertEqual(r.status_code, 502, r.content)
    self.assertNotIn('internal.host', r.content.decode())

  def test_generate_test_provider_exception_is_502(self):
    with self._provider_down():
      r = self.client.post(
        f'/assignments/{self.assignment.id}/generateTest/',
        {'targetFilename': 'a.py'}, format='json')
    self.assertEqual(r.status_code, 502, r.content)
    self.assertNotIn('internal.host', r.content.decode())

  def test_generate_comment_provider_exception_is_502(self):
    submission = self.assignment.submissions.first()
    f = SubmissionFileFactory(submission=submission, name='a.txt', data='hello')
    with self._provider_down():
      r = self.client.post(
        '/comments/generate/', {'file_id': f.id, 'start_line': 0, 'end_line': 0}, format='json')
    self.assertEqual(r.status_code, 502, r.content)
    self.assertNotIn('internal.host', r.content.decode())
