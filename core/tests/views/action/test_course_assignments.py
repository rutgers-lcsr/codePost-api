# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""GET /courses/{id}/assignments/ — the bulk replacement for the per-id fan-out.

The load-bearing contract: for every persona, the id-set the bulk action returns must
equal the set of assignments whose per-id retrieve returns 200, and each object must
serialize with the same field set the per-id endpoint would use for that caller."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.factories import *
from core.tests.utils import request_as, setUpBase
from core.tests.views.personas import Persona

ALL_STATES = ('draft', 'visible', 'preview', 'published', 'closed', 'archived')
STUDENT_STATES = ('visible', 'preview', 'published', 'closed')


class TestCourseAssignmentsAction(APITestCase):

  def setUp(self):
    setUpBase(self)
    self.endpoint = reverse("course-assignments", args=[self.course.id])

  def _make(self, name, state, **kwargs):
    return AssignmentFactory(course=self.course, name=name, state=state, **kwargs)

  def _bulk(self, user):
    response = request_as('read', user, self.endpoint)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    return response.data

  def _bulk_ids(self, user):
    return {a['id'] for a in self._bulk(user)}

  def _retrievable_ids(self, user):
    """Ids whose per-id GET /assignments/{id}/ returns 200 for this user."""
    ids = set()
    for assignment in self.course.assignments.all():
      response = request_as('read', user, reverse("assignment-detail", args=[assignment.id]))
      if response.status_code == status.HTTP_200_OK:
        ids.add(assignment.id)
    return ids

  # ── The parity contract ────────────────────────────────────────────────────

  def test_bulk_set_equals_per_id_retrievable_set_per_persona(self):
    for state in ALL_STATES:
      self._make(f"a-{state}", state)
    hidden = self._make("a-section-hidden", 'published')

    student = Persona.STUDENT_OF_COURSE(self)
    section = SectionFactory(course=self.course, name="P99-hidden")
    section.students.add(student)
    hidden.hideFrom.add(section)

    personas = {
        'admin': Persona.ADMIN_OF_COURSE(self),
        'grader': Persona.GRADER_OF_COURSE(self),
        'supergrader': Persona.SUPERGRADER_OF_COURSE(self),
        'student': student,
    }
    for name, user in personas.items():
      self.assertEqual(self._bulk_ids(user), self._retrievable_ids(user),
                       f"bulk set diverges from per-id behaviour for {name}")

  # ── Filtering ──────────────────────────────────────────────────────────────

  def test_student_sees_only_student_visible_states(self):
    student = Persona.STUDENT_OF_COURSE(self)
    by_state = {state: self._make(f"a-{state}", state) for state in ALL_STATES}

    ids = self._bulk_ids(student)
    for state in STUDENT_STATES:
      self.assertIn(by_state[state].id, ids, f"{state} must be listed")
    for state in ('draft', 'archived'):
      self.assertNotIn(by_state[state].id, ids, f"{state} must be omitted")

  def test_section_hidden_assignment_omitted_for_student_only(self):
    student = Persona.STUDENT_OF_COURSE(self)
    # Persona.STUDENT_OF_COURSE always returns the first student — make a distinct one.
    other_student = StudentFactory(profile__organization=self.course.organization)
    self.course.students.add(other_student)
    hidden = self._make("a-hidden", 'published')
    section = SectionFactory(course=self.course, name="P99-hidden")
    section.students.add(student)
    hidden.hideFrom.add(section)

    self.assertNotIn(hidden.id, self._bulk_ids(student))
    self.assertIn(hidden.id, self._bulk_ids(other_student))

  def test_staff_see_draft_and_archived(self):
    grader = Persona.GRADER_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)
    draft = self._make("a-draft", 'draft')
    archived = self._make("a-archived", 'archived')
    for user in (grader, admin):
      ids = self._bulk_ids(user)
      self.assertIn(draft.id, ids)
      self.assertIn(archived.id, ids)

  # ── Access ─────────────────────────────────────────────────────────────────

  def test_non_member_gets_403(self):
    outsider = Persona.STUDENT_OF_OTHER_COURSE(self)
    response = request_as('read', outsider, self.endpoint)
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_org_staff_non_member_gets_empty_list(self):
    # An org-staff user who is not a course member can read the course object, but
    # every per-id assignment retrieve 403s for them (AssignmentPermissions has no
    # org-staff arm). The bulk action mirrors the per-id behaviour: 200 with [].
    staff = Persona.GRADER_OF_ORG(self)
    staff.profile.isOrgStaff = True
    staff.profile.organization = self.course.organization
    staff.profile.save()
    self._make("a-visible", 'published')

    self.assertEqual(self._bulk(staff), [])
    self.assertEqual(self._retrievable_ids(staff), set())

  # ── Serializer parity ──────────────────────────────────────────────────────

  def _per_id_body(self, user, assignment_id):
    response = request_as('read', user, reverse("assignment-detail", args=[assignment_id]))
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    return response.data

  def test_each_object_matches_per_id_body_per_role(self):
    assignment = self._make("a-parity", 'published')
    for persona in (Persona.ADMIN_OF_COURSE, Persona.GRADER_OF_COURSE, Persona.STUDENT_OF_COURSE):
      user = persona(self)
      bulk_obj = next(a for a in self._bulk(user) if a['id'] == assignment.id)
      self.assertEqual(dict(bulk_obj), dict(self._per_id_body(user, assignment.id)),
                       f"payload diverges from per-id for {persona}")

  def test_student_payload_has_no_staff_fields_admin_has_stats(self):
    self._make("a-fields", 'published')
    student = Persona.STUDENT_OF_COURSE(self)
    admin = Persona.ADMIN_OF_COURSE(self)
    grader = Persona.GRADER_OF_COURSE(self)

    student_obj = self._bulk(student)[0]
    for leaked in ('ai_system_prompt', 'anonymousGrading', 'submissions_count'):
      self.assertNotIn(leaked, student_obj)

    # The stats+summary serializer is distinguished by the submissions_* summary fields.
    admin_obj = next(a for a in self._bulk(admin) if a['name'] == "a-fields")
    self.assertIn('submissions_count', admin_obj)

    grader_obj = next(a for a in self._bulk(grader) if a['name'] == "a-fields")
    self.assertNotIn('submissions_count', grader_obj)

  def test_student_feedback_axis_switches_serializer(self):
    student = Persona.STUDENT_OF_COURSE(self)

    hidden_fb = self._make("a-fb-hidden", 'published', feedbackStatus='hidden')
    released_fb = self._make("a-fb-released", 'published', feedbackStatus='released')

    by_name = {a['name']: a for a in self._bulk(student)}
    # Feedback closed: base student serializer — no stats fields at all.
    self.assertNotIn('mean', by_name[hidden_fb.name])
    # Feedback open, course stats off (factory default): NoStats variant.
    self.assertFalse(self.course.showStudentsStatistics)
    self.assertNotIn('mean', by_name[released_fb.name])

    self.course.showStudentsStatistics = True
    self.course.save()
    by_name = {a['name']: a for a in self._bulk(student)}
    self.assertIn('mean', by_name[released_fb.name], "stats appear once course opts in")
    self.assertNotIn('mean', by_name[hidden_fb.name], "closed feedback stays statless")
