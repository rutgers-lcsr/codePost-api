# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""AI comment generation: context building (build_context_from_file) and the
POST /comments/generate/ endpoint. The AI provider is mocked at
``AIService._dispatch_provider``; no real provider is ever called."""
import base64
import json
from unittest.mock import AsyncMock, patch

import factory
import pymupdf
from django.db.models.signals import post_save
from rest_framework.test import APITestCase

from core.models import SubmissionFile
from core.services.ai_service import build_context_from_file
from core.tests.factories import (
  CourseFactory,
  RubricCategoryFactory,
  RubricCommentFactory,
  SubmissionFileFactory,
)


def _pdf_data_uri(pages):
  doc = pymupdf.open()
  for text in pages:
    page = doc.new_page()
    page.insert_text((72, 72), text)
  raw = doc.tobytes()
  doc.close()
  return "data:application/pdf;base64," + base64.b64encode(raw).decode()


def _notebook(cells):
  return json.dumps({
    'cells': [{'cell_type': 'code', 'source': c, 'outputs': [], 'metadata': {}} for c in cells],
    'metadata': {}, 'nbformat': 4, 'nbformat_minor': 5,
  })


class AICommentGenerationBase(APITestCase):

  def setUp(self):
    with factory.django.mute_signals(post_save):
      self.course = CourseFactory()
    self.course.ai_use_own_settings = True
    self.course.ai_provider = 'openai'
    self.course.ai_api_key = 'test-key'
    self.course.save()
    self.assignment = self.course.assignments.first()
    self.submission = self.assignment.submissions.first()
    self.grader = self.course.courseAdmins.first()

  def make_file(self, name, data):
    f = SubmissionFileFactory(submission=self.submission, name='placeholder.txt', data='x')
    # queryset update skips model validation, which would reject a corrupt .pdf
    SubmissionFile.objects.filter(pk=f.pk).update(name=name, data=data)
    f.refresh_from_db()
    return f

  def post(self, **body):
    self.client.force_authenticate(user=self.grader)
    return self.client.post('/comments/generate/', body, format='json')


class BuildContextTests(AICommentGenerationBase):

  def test_empty_notebook_degrades(self):
    f = self.make_file('empty.ipynb', _notebook([]))
    context = build_context_from_file(f, 0, 0)
    self.assertEqual(context.selected_content, '')

  def test_notebook_with_null_cells_degrades(self):
    f = self.make_file('nullcells.ipynb', json.dumps({'cells': None}))
    context = build_context_from_file(f, 0, 0)
    self.assertEqual(context.selected_content, '')

  def test_single_line_selection_uses_end_char_from_line_start(self):
    f = self.make_file('a.txt', 'hello world foo')
    context = build_context_from_file(f, 0, 0, 6, 11)
    self.assertEqual(context.selected_content, 'world')

  def test_multi_line_selection_char_offsets(self):
    f = self.make_file('a.txt', 'hello world\nsecond line here')
    context = build_context_from_file(f, 0, 1, 6, 6)
    self.assertEqual(context.selected_content, 'world\nsecond')

  def test_corrupt_pdf_degrades(self):
    f = self.make_file('bad.pdf', 'this is not a pdf')
    context = build_context_from_file(f, 1, 1)
    self.assertIn('Could not', context.selected_content)

  def test_undecodable_base64_pdf_degrades(self):
    f = self.make_file('bad.pdf', 'data:application/pdf;base64,@@@')
    context = build_context_from_file(f, 1, 1)
    self.assertIn('Could not', context.selected_content)

  def test_pdf_page_range_is_one_based_and_valid(self):
    f = self.make_file('two.pdf', _pdf_data_uri(['PAGE-ONE', 'PAGE-TWO']))
    context = build_context_from_file(f, 2, 2)
    self.assertIn('PAGE-TWO', context.selected_content)
    self.assertNotIn('PAGE-ONE', context.selected_content)

  def test_pdf_page_range_out_of_bounds_raises_value_error(self):
    f = self.make_file('two.pdf', _pdf_data_uri(['PAGE-ONE', 'PAGE-TWO']))
    for start, end in [(0, 1), (1, 3), (2, 1)]:
      with self.subTest(start=start, end=end):
        with self.assertRaises(ValueError):
          build_context_from_file(f, start, end)


class GenerateEndpointTests(AICommentGenerationBase):

  def _provider(self, text='Nice work.'):
    return patch('core.services.ai_service.AIService._dispatch_provider',
                 new=AsyncMock(return_value=(text, 1, 1, 2, 0)))

  def test_empty_notebook_generates(self):
    f = self.make_file('empty.ipynb', _notebook([]))
    with self._provider():
      resp = self.post(file_id=f.id, start_line=0, end_line=0)
    self.assertEqual(resp.status_code, 200, resp.content)
    self.assertEqual(resp.data['text'], 'Nice work.')

  def test_corrupt_pdf_generates(self):
    f = self.make_file('bad.pdf', 'not a pdf')
    with self._provider():
      resp = self.post(file_id=f.id, start_line=1, end_line=1)
    self.assertEqual(resp.status_code, 200, resp.content)

  def test_pdf_page_out_of_range_is_400(self):
    f = self.make_file('two.pdf', _pdf_data_uri(['A', 'B']))
    for start, end in [(0, 1), (1, 3), (2, 1)]:
      with self.subTest(start=start, end=end), self._provider():
        resp = self.post(file_id=f.id, start_line=start, end_line=end)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIsInstance(resp.data['detail'], str)

  def test_non_integer_line_numbers_are_400(self):
    f = self.make_file('a.txt', 'hello')
    for body in [
      dict(start_line='abc', end_line=0),
      dict(start_line=0, end_line=[1]),
      dict(start_line=0, end_line=0, start_char='x', end_char=2),
      dict(start_line=0, end_line=0, points='lots'),
    ]:
      with self.subTest(body=body), self._provider():
        resp = self.post(file_id=f.id, **body)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIsInstance(resp.data['detail'], str)

  def test_numeric_strings_are_accepted(self):
    f = self.make_file('a.txt', 'hello')
    with self._provider():
      resp = self.post(file_id=f.id, start_line='0', end_line='0')
    self.assertEqual(resp.status_code, 200, resp.content)

  def test_rubric_comment_from_other_assignment_is_404(self):
    with factory.django.mute_signals(post_save):
      other = CourseFactory(name='cos226', period='f2021', organization__name='Other')
    other_rubric = RubricCommentFactory(
      text='SECRET-OTHER-COURSE-RUBRIC',
      category=RubricCategoryFactory(assignment=other.assignments.first()),
    )
    f = self.make_file('a.txt', 'hello')
    mock = AsyncMock(return_value=('x', 1, 1, 2, 0))
    with patch('core.services.ai_service.AIService._dispatch_provider', new=mock):
      resp = self.post(file_id=f.id, start_line=0, end_line=0, rubric_comment_id=other_rubric.id)
    self.assertEqual(resp.status_code, 404, resp.content)
    self.assertIsInstance(resp.data['detail'], str)
    mock.assert_not_called()

  def test_rubric_comment_non_numeric_is_400_or_404(self):
    f = self.make_file('a.txt', 'hello')
    with self._provider():
      resp = self.post(file_id=f.id, start_line=0, end_line=0, rubric_comment_id='abc')
    self.assertIn(resp.status_code, (400, 404), resp.content)
    self.assertIsInstance(resp.data['detail'], str)

  def test_own_assignment_rubric_comment_is_used(self):
    rubric = RubricCommentFactory(
      text='OWN-RUBRIC-TEXT', category=RubricCategoryFactory(assignment=self.assignment))
    f = self.make_file('a.txt', 'hello')
    mock = AsyncMock(return_value=('x', 1, 1, 2, 0))
    with patch('core.services.ai_service.AIService._dispatch_provider', new=mock):
      resp = self.post(file_id=f.id, start_line=0, end_line=0, rubric_comment_id=rubric.id)
    self.assertEqual(resp.status_code, 200, resp.content)
    self.assertIn('OWN-RUBRIC-TEXT', ''.join(str(a) for a in mock.call_args.args))
