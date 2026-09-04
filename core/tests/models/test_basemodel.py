# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Tests for BaseModel.save() update_fields handling:

- `modified` must actually persist on updates (it is stamped before the UPDATE
  and included in update_fields).
- Caller-supplied update_fields must be honored (plus `modified`), and must skip
  the change-diff SELECT entirely.
- The change-diff must compare FKs by raw id (attname) without lazy-loading the
  related objects.
- A no-op save must keep update_fields empty, skipping the UPDATE and signals.
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from core.models import Course, Section
from core.tests.factories import OrganizationFactory, CourseFactory, SectionFactory


class TestBaseModelSave(APITestCase):

  def setUp(self):
    self.org = OrganizationFactory()
    self.course = CourseFactory(name='bmsave', period='s2020', organization=self.org)

  def test_modified_persists_on_update(self):
    before = Course.objects.get(pk=self.course.pk).modified
    self.course.name = 'bmsave-renamed'
    self.course.save()
    fresh = Course.objects.get(pk=self.course.pk)
    self.assertEqual(fresh.name, 'bmsave-renamed')
    self.assertGreater(fresh.modified, before)

  def test_caller_update_fields_are_honored(self):
    self.course.name = 'bmsave-name'
    self.course.period = 's2099'
    before = Course.objects.get(pk=self.course.pk)
    self.course.save(update_fields=['name'])
    fresh = Course.objects.get(pk=self.course.pk)
    # Only the declared field (plus modified) is written; the undeclared change is not.
    self.assertEqual(fresh.name, 'bmsave-name')
    self.assertEqual(fresh.period, before.period)
    self.assertGreater(fresh.modified, before.modified)

  def test_caller_update_fields_skip_diff_select(self):
    self.course.name = 'bmsave-fast'
    with CaptureQueriesContext(connection) as ctx:
      self.course.save(update_fields=['name'])
    course_table = Course._meta.db_table
    selects_on_course = [q['sql'] for q in ctx.captured_queries
                         if q['sql'].startswith('SELECT') and course_table in q['sql']]
    self.assertEqual(selects_on_course, [],
                     msg="save(update_fields=...) must not re-fetch the row for a diff")

  def test_diff_does_not_load_fk_relations(self):
    section = SectionFactory(course=self.course, name='bm-sec')
    section.name = 'bm-sec-renamed'
    with CaptureQueriesContext(connection) as ctx:
      section.save()
    course_table = Course._meta.db_table
    selects_on_course = [q['sql'] for q in ctx.captured_queries
                         if q['sql'].startswith('SELECT') and course_table in q['sql']]
    self.assertEqual(selects_on_course, [],
                     msg="the change-diff must compare FKs by id, not load the related row")
    fresh = Section.objects.get(pk=section.pk)
    self.assertEqual(fresh.name, 'bm-sec-renamed')

  def test_noop_save_skips_update_and_signals(self):
    before = Course.objects.get(pk=self.course.pk).modified
    with CaptureQueriesContext(connection) as ctx:
      self.course.save()
    updates = [q['sql'] for q in ctx.captured_queries if q['sql'].startswith('UPDATE')]
    self.assertEqual(updates, [], msg="a save with no changes must skip the UPDATE")
    self.assertEqual(Course.objects.get(pk=self.course.pk).modified, before)
