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
- A new object given its pk up front is an insert, not an update of a row that
  does not exist yet; clearing the pk of a loaded object still saves a copy.
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from core.models import Course, Organization, Section
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

  def test_create_with_explicit_pk_inserts_the_row(self):
    org = Organization.objects.create(id=4242, name='bm-explicit', shortname='BMX')
    fresh = Organization.objects.get(pk=4242)
    self.assertEqual(fresh.name, 'bm-explicit')
    self.assertEqual(fresh.created, org.created)
    self.assertEqual(fresh.modified, org.modified)

  def test_get_or_create_with_explicit_pk(self):
    _, created = Organization.objects.get_or_create(pk=4343, defaults={'name': 'bm-goc', 'shortname': 'BMG'})
    self.assertTrue(created)
    again, created_again = Organization.objects.get_or_create(pk=4343)
    self.assertFalse(created_again)
    self.assertEqual(again.name, 'bm-goc')

  def test_clearing_pk_of_a_loaded_object_saves_a_copy(self):
    # The pattern copy_assignment and copy_rubric use.
    copy = Course.objects.get(pk=self.course.pk)
    copy.pk = None
    copy.period = 's2101'
    copy.save()
    self.assertNotEqual(copy.pk, self.course.pk)
    self.assertEqual(Course.objects.filter(name='bmsave').count(), 2)
