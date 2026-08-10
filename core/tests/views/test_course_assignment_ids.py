# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The get_assignments contract: every assignment ID a student receives from
GET /courses/{id}/ must retrieve 200, and every omitted one must 403 — so clients can
fan out over course.assignments without hitting scary errors (core/serializers/course.py)."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Assignment
from core.tests.factories import *
from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona


class TestCourseAssignmentIds(APITestCase):

  def setUp(self):
    setUpBase(self)
    self.endpoint = reverse("course-detail", args=[self.course.id])
    self.base_assignment = Assignment.objects.get(id=self.DB['Assignment'].id)

  def _make(self, name, state):
    return AssignmentFactory(course=self.course, name=name, state=state)

  def _ids_for(self, user):
    response = request_as('read', user, self.endpoint)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    return response.data['assignments']

  def test_student_sees_only_student_visible_states(self):
    student = Persona.STUDENT_OF_COURSE(self)
    by_state = {state: self._make(f"a-{state}", state)
                for state in ('draft', 'visible', 'preview', 'published', 'closed', 'archived')}

    ids = self._ids_for(student)
    for state in ('visible', 'preview', 'published', 'closed'):
      self.assertIn(by_state[state].id, ids, f"{state} must be listed")
    for state in ('draft', 'archived'):
      self.assertNotIn(by_state[state].id, ids, f"{state} must be omitted")

    # Contract: listed IDs retrieve 200; omitted IDs 403.
    for state in ('visible', 'preview', 'published', 'closed'):
      response = request_as('read', student,
                            reverse("assignment-detail", args=[by_state[state].id]))
      self.assertEqual(response.status_code, status.HTTP_200_OK, f"retrieve {state}")
    for state in ('draft', 'archived'):
      response = request_as('read', student,
                            reverse("assignment-detail", args=[by_state[state].id]))
      self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, f"retrieve {state}")

  def test_section_hidden_assignment_omitted_and_403s(self):
    student = Persona.STUDENT_OF_COURSE(self)
    hidden = self._make("a-hidden-section", 'published')
    section = SectionFactory(course=self.course, name="P99-hidden")
    section.students.add(student)
    hidden.hideFrom.add(section)

    ids = self._ids_for(student)
    self.assertNotIn(hidden.id, ids)
    response = request_as('read', student, reverse("assignment-detail", args=[hidden.id]))
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_other_section_student_unaffected(self):
    student = Persona.STUDENT_OF_COURSE(self)
    assignment = self._make("a-other-section", 'published')
    section = SectionFactory(course=self.course, name="P99-hidden")  # student NOT in it
    assignment.hideFrom.add(section)

    self.assertIn(assignment.id, self._ids_for(student))
    response = request_as('read', student, reverse("assignment-detail", args=[assignment.id]))
    self.assertEqual(response.status_code, status.HTTP_200_OK)

  def test_staff_see_everything(self):
    grader = Persona.GRADER_OF_COURSE(self)
    draft = self._make("a-staff-draft", 'draft')
    archived = self._make("a-staff-archived", 'archived')

    ids = self._ids_for(grader)
    self.assertIn(draft.id, ids)
    self.assertIn(archived.id, ids)
