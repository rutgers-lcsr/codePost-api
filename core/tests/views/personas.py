# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.tests.factories import *
from enum import Enum
from functools import partial


class Persona(Enum):

  ##############################################
  # Course Level Personas
  ##############################################

  # Make Enum function value callable
  def __call__(self, *args):
    return self.value(*args)

  def admin_of_org(self):
    user = AdminFactory()
    self.assertTrue(user.profile.canCreateCourses)
    self.assertTrue(user.profile.canModifyRosters)
    return user

  ADMIN_OF_ORG = partial(admin_of_org)

  def grader_of_org(self):
    user = GraderFactory()
    self.assertFalse(user.profile.canCreateCourses)
    self.assertFalse(user.profile.canModifyRosters)
    return user

  GRADER_OF_ORG = partial(grader_of_org)

  def student_of_org(self):
    user = StudentFactory()
    self.assertFalse(user.profile.canCreateCourses)
    self.assertFalse(user.profile.canModifyRosters)
    return user

  STUDENT_OF_ORG = partial(student_of_org)

  def admin_of_course(self):
    user = self.course.courseAdmins.first()
    self.assertIn(user, self.course.courseAdmins.all())
    return user

  ADMIN_OF_COURSE = partial(admin_of_course)

  def admin_of_other_course(self):
    user = self.other_course.courseAdmins.first()
    self.assertIn(user, self.other_course.courseAdmins.all())
    self.assertNotIn(user, self.course.courseAdmins.all())
    self.assertEqual(user.profile.organization, self.course.organization)
    return user

  ADMIN_OF_OTHER_COURSE = partial(admin_of_other_course)

  def admin_of_other_org(self):
    user = self.other_org_course.courseAdmins.first()
    self.assertIn(user, self.other_org_course.courseAdmins.all())
    self.assertNotIn(user, self.course.courseAdmins.all())
    self.assertNotEqual(user.profile.organization, self.course.organization)
    return user

  ADMIN_OF_OTHER_ORG = partial(admin_of_other_org)

  def inactive_admin_of_course(self):
    user = self.course.inactive_courseAdmins.first()
    self.assertIn(user, self.course.inactive_courseAdmins.all())
    self.assertNotIn(user, self.course.courseAdmins.all())
    return user

  INACTIVE_ADMIN_OF_COURSE = partial(inactive_admin_of_course)

  def grader_of_course(self):
    user = self.course.graders.first()
    self.assertIn(user, self.course.graders.all())
    return user

  GRADER_OF_COURSE = partial(grader_of_course)

  def grader_of_other_course(self):
    user = self.other_course.graders.first()
    self.assertIn(user, self.other_course.graders.all())
    self.assertNotIn(user, self.course.graders.all())
    self.assertEqual(user.profile.organization, self.course.organization)
    return user

  GRADER_OF_OTHER_COURSE = partial(grader_of_other_course)

  def grader_of_other_org(self):
    user = self.other_org_course.graders.first()
    self.assertIn(user, self.other_org_course.graders.all())
    self.assertNotIn(user, self.course.graders.all())
    self.assertNotEqual(user.profile.organization, self.course.organization)
    return user

  GRADER_OF_OTHER_ORG = partial(grader_of_other_org)

  def inactive_grader_of_course(self):
    user = self.course.inactive_graders.first()
    self.assertIn(user, self.course.inactive_graders.all())
    self.assertNotIn(user, self.course.graders.all())
    return user

  INACTIVE_GRADER_OF_COURSE = partial(inactive_grader_of_course)

  def student_of_course(self):
    user = self.course.students.first()
    self.assertIn(user, self.course.students.all())
    return user

  STUDENT_OF_COURSE = partial(student_of_course)

  def student_of_other_course(self):
    user = self.other_course.students.first()
    self.assertIn(user, self.other_course.students.all())
    self.assertNotIn(user, self.course.students.all())
    self.assertEqual(user.profile.organization, self.course.organization)
    return user

  STUDENT_OF_OTHER_COURSE = partial(student_of_other_course)

  def student_of_other_org(self):
    user = self.other_org_course.students.first()
    self.assertIn(user, self.other_org_course.students.all())
    self.assertNotIn(user, self.course.students.all())
    self.assertNotEqual(user.profile.organization, self.course.organization)
    return user

  STUDENT_OF_OTHER_ORG = partial(student_of_other_org)

  def inactive_student_of_course(self):
    user = self.course.inactive_students.first()
    self.assertIn(user, self.course.inactive_students.all())
    self.assertNotIn(user, self.course.students.all())
    return user

  INACTIVE_STUDENT_OF_COURSE = partial(inactive_student_of_course)

  def supergrader_of_course(self):
    user = self.course.superGraders.first()
    self.assertIn(user, self.course.superGraders.all())
    return user

  SUPERGRADER_OF_COURSE = partial(supergrader_of_course)

  def supergrader_of_other_course(self):
    user = self.other_course.superGraders.first()
    self.assertIn(user, self.other_course.superGraders.all())
    self.assertNotIn(user, self.course.superGraders.all())
    self.assertEqual(user.profile.organization, self.course.organization)
    return user

  SUPERGRADER_OF_OTHER_COURSE = partial(supergrader_of_other_course)

  def supergrader_of_other_org(self):
    user = self.other_org_course.superGraders.first()
    self.assertIn(user, self.other_org_course.superGraders.all())
    self.assertNotIn(user, self.course.superGraders.all())
    self.assertNotEqual(user.profile.organization, self.course.organization)
    return user

  SUPERGRADER_OF_OTHER_ORG = partial(supergrader_of_other_org)

  ##############################################
  # Submission Level Personas
  ##############################################

  def grader_of_sub(self):
    submission = Submission.objects.filter(assignment__course=self.course).first()
    user = self.course.graders.first()
    submission.grader = user
    submission.save()
    self.assertEqual(submission.grader, user)
    self.assertIn(user, self.course.graders.all())
    return user

  GRADER_OF_SUB = partial(grader_of_sub)

  def grader_of_other_sub(self):
    assignment = Assignment.objects.filter(course=self.course).first()
    newSubmission = Submission.objects.create(assignment=assignment)
    user = self.course.graders.first()
    student = self.course.students.last()

    newSubmission.grader = user
    newSubmission.save()

    submission = Submission.objects.filter(assignment__course=self.course).first()

    self.assertIn(user, self.course.graders.all())
    self.assertEqual(newSubmission.grader, user)
    self.assertNotEqual(submission.grader, user)
    self.assertEqual(submission.assignment, newSubmission.assignment)
    self.assertNotEqual(submission, newSubmission)
    return user

  GRADER_OF_OTHER_SUB = partial(grader_of_other_sub)

  def inactive_grader_of_sub(self):
    submission = Submission.objects.filter(assignment__course=self.course).first()
    user = self.course.inactive_graders.first()
    submission.grader = user
    submission.save()
    self.assertNotIn(user, self.course.graders.all())
    self.assertIn(user, self.course.inactive_graders.all())
    self.assertEqual(submission.grader, user)
    return user

  INACTIVE_GRADER_OF_SUB = partial(inactive_grader_of_sub)

  def section_leader_of_sub(self):
    section = Section.objects.filter(course=self.course).first()
    user = self.course.graders.first()
    student = self.course.students.last()
    section.leaders.set([user])
    section.students.set([student])
    section.save()

    submission = Submission.objects.filter(assignment__course=self.course).first()
    submission.students.set([student])
    submission.save()

    self.assertIn(user, self.course.graders.all())
    self.assertNotEqual(submission.grader, user)
    self.assertEqual(submission.students.first().student_sections.first(), user.leader_sections.first())
    return user

  SECTION_LEADER_OF_SUB = partial(section_leader_of_sub)

  def section_leader_of_other_sub(self):
    assignment = Assignment.objects.filter(course=self.course).first()
    section = Section.objects.filter(course=self.course).first()
    user = self.course.graders.first()
    student = self.course.students.last()
    section.leaders.set([user])
    section.students.set([student])
    section.save()

    newSubmission = Submission.objects.create(assignment=assignment)
    newSubmission.students.set([student])
    newSubmission.save()

    submission = Submission.objects.filter(assignment__course=self.course).first()

    self.assertIn(user, self.course.graders.all())
    self.assertNotEqual(submission.grader, user)
    self.assertNotEqual(newSubmission.grader, user)
    self.assertEqual(newSubmission.students.first().student_sections.first(), user.leader_sections.first())
    self.assertEqual(submission.assignment, newSubmission.assignment)
    self.assertNotEqual(submission, newSubmission)
    return user

  SECTION_LEADER_OF_OTHER_SUB = partial(section_leader_of_other_sub)

  def inactive_section_leader_of_sub(self):
    section = Section.objects.filter(course=self.course).first()
    user = self.course.inactive_graders.first()
    student = self.course.students.last()
    section.leaders.set([user])
    section.students.set([student])
    section.save()

    submission = Submission.objects.filter(assignment__course=self.course).first()
    submission.students.set([student])
    submission.save()

    self.assertNotIn(user, self.course.graders.all())
    self.assertIn(user, self.course.inactive_graders.all())
    self.assertNotEqual(submission.grader, user)
    self.assertEqual(submission.students.first().student_sections.first(), user.leader_sections.first())
    return user

  INACTIVE_SECTION_LEADER_OF_SUB = partial(inactive_section_leader_of_sub)

  def student_of_sub(self):
    submission = Submission.objects.filter(assignment__course=self.course).first()
    user = self.course.students.last()
    submission.students.set([user])
    submission.save()

    self.assertIn(user, submission.students.all())

    return user

  STUDENT_OF_SUB = partial(student_of_sub)

  def student_of_other_sub(self):
    assignment = Assignment.objects.filter(course=self.course).first()
    newSubmission = Submission.objects.create(assignment=assignment)
    user = self.course.students.last()

    newSubmission.students.set([user])
    newSubmission.save()

    submission = Submission.objects.filter(assignment__course=self.course).first()

    self.assertIn(user, self.course.students.all())
    self.assertIn(user, newSubmission.students.all())
    self.assertNotIn(user, submission.students.all())
    self.assertEqual(submission.assignment, newSubmission.assignment)
    self.assertNotEqual(submission, newSubmission)
    return user

  STUDENT_OF_OTHER_SUB = partial(student_of_other_sub)

  def inactive_student_of_sub(self):
    submission = Submission.objects.filter(assignment__course=self.course).first()
    user = self.course.inactive_students.last()
    submission.students.set([user])
    submission.save()

    self.assertIn(user, submission.students.all())
    self.assertNotIn(user, self.course.students.all())
    self.assertIn(user, self.course.inactive_students.all())
    return user

  INACTIVE_STUDENT_OF_SUB = partial(inactive_student_of_sub)
