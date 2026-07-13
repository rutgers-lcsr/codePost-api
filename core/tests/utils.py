# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import *
from core.tests.factories import *

from rest_framework.test import APIClient

PASSWORD = 'rootabega'

# Helpful Assert Methods
# https://docs.python.org/3/library/unittest.html#assert-methods


def request_as(method, user, endpoint, payload=None):
  client = APIClient()
  client.force_authenticate(user=user)

  if method == 'create':
    return client.post(endpoint, payload, format='json')
  elif method in ['read', 'list']:
    return client.get(endpoint)
  elif method == 'update':
    return client.patch(endpoint, payload, format='json')
  elif method == 'delete':
    return client.delete(endpoint)
  raise ValueError(f"Unknown request method: '{method}'. Expected 'create', 'read', 'list', 'update', or 'delete'.")


def setUpBase(self):
  course = CourseFactory(name="cos126", period="s2020", organization__name="Princeton")
  other_course = CourseFactory(name="cos226", period="s2020", organization__name="Princeton")
  other_org_course = CourseFactory(name="cs101", period="s2020", organization__name="Harvard")
  self.course = course
  self.other_course = other_course
  self.other_org_course = other_org_course

  self.DB = {
      "Organization": course.organization,
      "Course": course,
      "Other_Course": other_course,
      "Other_Org_Course": other_org_course,
      "Assignment": course.assignments.first(),
      "Submission": course.assignments.first().submissions.first(),
      "File": course.assignments.first().submissions.first().files.first(),
      "Section": course.sections.first(),
      "RubricCategory": course.assignments.first().rubricCategories.first(),
      "RubricComment": course.assignments.first().rubricCategories.first().rubricComments.first(),
      "Comment": course.assignments.first().submissions.first().files.first().comments.first()
  }

  self.PAYLOADS = {
      "Organization": {
          "create": {
              "name": "Caltech",
              "shortname": "caltech"
          },
          "update": {
              "name": "Calytech",
          }
      },
      "Course": {
          "create": {
              "name": 'COS126',
              "period": 'S2020'
          },
          "update": {
              "period": 'F2020'
          }
      },
      "Assignment": {
          "create": {
              "course": course.id,
              "name": 'New Assignment',
              "points": 25,
              "isReleased": False
          },
          "update": {
              "points": 30
          }
      },
      "Submission": {
          "create": {
              "assignment": course.assignments.first().id,
              "students": [course.students.first().username]
          },
          "update": {
              "students": [course.students.first().username],
              "grader": course.graders.first().username
          }
      },
      "File": {
          "create": {
              "submission": course.assignments.first().submissions.first().id,
              "name": "loops.java",
              "extension": ".java",
            "data": "System.out.println(loops)"
          },
          "update": {
              "name": "updated.java"
          }
      },
      "Section": {
          "create": {
              "course": course.id,
              "name": "S1",
              "leaders": [course.graders.first().username],
              "students": [course.students.first().username]
          },
          "update": {
              "name": "S2",
              "leaders": [],
              "students": []
          }
      },
      "RubricCategory": {
          "create": {
              "assignment": course.assignments.first().id,
              "name": "Style"
          },
          "update": {
              "name": "Updated category"
          }
      },
      "RubricComment": {
          "create": {
              "category": course.assignments.first().rubricCategories.first().id,
              "text": "New comment text",
              "pointDelta": 2
          },
          "update": {
              "text": "updated comment text"
          }
      },
      "Comment": {
          "create": {
              "file": course.assignments.first().submissions.first().files.first().id,
              "text": "comment text",
              "pointDelta": 1,
              "startLine": 0,
              "endLine": 0,
              "startChar": 1,
              "endChar": 5
          },
          "update": {
              "text": "updated text"
          }
      },
      "Course-roster": {
          "create": {

          },
          "update": {
              "students": []
          }
      },
      "Course-courseSettings": {
          "create": {

          },
          "update": {
              "showStudentsStatistics": True
          }
      },
      "Assignment-drawUnassigned": {
      },
      "Assignment-rubric": {
      },
      "Assignment-submissions": {
      },
  }

###
# Below only used in test_grade_calculation
# Eventually we can port to FactoryBoy and Faker
# https://factoryboy.readthedocs.io/en/latest/
# https://faker.readthedocs.io/en/latest/index.html
##

SUPERUSER_USERNAME = 'admin@admin.io'
SUPERUSER_EMAIL = 'admin@admin.io'
SUPERUSER_PASSWORD = 'rootabega'


def setUpClient(self):
  self.superuser = User.objects.create_superuser(SUPERUSER_USERNAME, SUPERUSER_EMAIL, SUPERUSER_PASSWORD)
  self.superuser.profile.canCreateCourses = True
  self.superuser.profile.canModifyRosters = True
  self.superuser.save()
  self.client.login(username=SUPERUSER_USERNAME, password=SUPERUSER_PASSWORD)


def setUpOrganization(self):
  organization = Organization.objects.create(name="South Harmon Institute of Technology", shortname="SHIT")
  self.superuser.profile.organization = organization
  self.superuser.save()
  return organization


def setUpCourse(self):
  organization = setUpOrganization(self)
  course = Course.objects.create(organization=organization, period="S2020", name="CS101")
  course.courseAdmins.set([self.superuser])
  course.graders.set([self.superuser])
  course.save()
  return course


def setUpAssignment(self, additiveGrading=False):
  course = setUpCourse(self)
  assignment = Assignment.objects.create(course=course, points=20, isReleased=True,
                                         name="loops", additiveGrading=additiveGrading)
  return assignment


def setUpAssignments(self):
  course = setUpCourse(self)
  assignment = [
      Assignment.objects.create(course=course, points=20, isReleased=True, name="loops"),
      Assignment.objects.create(course=course, points=20, isReleased=True, name="nbody"),
      Assignment.objects.create(course=course, points=20, isReleased=True, name="sierpinski")
  ]
  return assignment


def setUpSection(self):
  course = setUpCourse(self)
  section = Section.objects.create(name="P01", course=course)
  return section


def setUpSubmission(self):
  assignment = setUpAssignment(self)
  student = User.objects.create(username="student@gmail.com", email="student@gmail.com", password="rootabega")
  student.profile.organization = assignment.course.organization
  assignment.course.students.add(student)
  student.save()

  submission = Submission.objects.create(assignment=assignment)
  submission.students.add(student)
  submission.save()

  return submission


def setUpFile(self, name="hello.java", path="", submission=None, created=None):
  if created is None:
    created = timezone.now()
  thisSubmission = setUpSubmission(self) if submission is None else submission
  code = "public static void main {\nSystem.out.println('Hello, World!')\n}"
  file = SubmissionFile.objects.create(
      name=name,
      path=path,
      data=code,
      submission=thisSubmission,
      extension='.java',
      created=created,
  )
  return file


def setUpComment(self, file=None, pointDelta=1, rubricComment=None):
  thisFile = setUpFile(self) if file is None else file
  comment = Comment.objects.create(text="good job!", author=self.superuser, file=thisFile, startChar=1,
                                   endChar=2, startLine=1, endLine=1, pointDelta=pointDelta, rubricComment=rubricComment)
  return comment


def setUpRubricCategory(self, name="General", pointLimit=10, assignment=None):
  thisAssignment = setUpAssignment(self) if assignment is None else assignment
  rubricCategory = RubricCategory.objects.create(assignment=thisAssignment, name=name, pointLimit=pointLimit)
  return rubricCategory


def setUpRubricComment(self, category=None, pointDelta=2):
  thisRubricCategory = setUpRubricCategory(self) if category is None else category
  rubricComment = RubricComment.objects.create(
      text='Missing a semicolon', pointDelta=pointDelta, category=thisRubricCategory)
  return rubricComment


def setUpRoster(self):
  course = setUpCourse(self)

  student = User.objects.create(username="student1@gmail.com", email="student1@gmail.com", password="rootabega")
  student.profile.organization = course.organization
  student.save()

  grader = User.objects.create(username="grader1@gmail.com", email="grader1@gmail.com", password="rootabega")
  grader.profile.organization = course.organization
  grader.save()

  _students = [student.email]
  _graders = [grader.email]
  return course
