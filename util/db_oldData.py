from django.contrib.auth.models import User
from core.models import Profile
from core.models import Organization, Course
from core.models import Section, Assignment
from core.models import Submission, File, Comment
from core.models import RubricCategory, RubricComment
import random
import json

# Set up users
princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
f_users = open('./toMigrate/cleaned_users.txt', 'r')
users = json.loads(f_users.read())
for email in users:
  if len(email.split('@')) > 1:
    me = User.objects.create(username=email, email=email)
    me.save()

print("Created users.")

# Add james, rich, vinay as admins
superUsers = []
for name in ['richard@codepost.io', 'vinay@codepost.io', 'james@codepost.io']:
    newUser = User.objects.create(username=name, email=name, password="rootabega")
    newUser.profile.canCreateCourses = True
    newUser.profile.canModifyRosters = True
    newUser.set_password('rootabega')
    newUser.profile.organization = princeton
    newUser.is_superuser = True
    newUser.is_staff = True
    newUser.save()
    superUsers.append(newUser)

# Set up courses
f_courses = open('./toMigrate/cleaned_data.txt', 'r')
courses = json.loads(f_courses.read())
i = 1
for oldCourse in courses:
  name = oldCourse['name'].split('_')[0]
  period = oldCourse['name'].split('_')[1]
  course = Course.objects.create(name=name, period=period, organization=princeton)
  for student in oldCourse['students']:
      if (student not in ['vayyala@princeton.edu', 'jaevans@princeton.edu', 'rfreling@princeton.edu']):
          course.students.add(User.objects.get(email=student))
  for grader in oldCourse['graders']:
      course.graders.add(User.objects.get(email=grader))
  for admin in oldCourse['admins']:
      admin = User.objects.get(email=admin)
      course.courseAdmins.add(admin)
      admin.profile.canCreateCourses = True
      admin.profile.canModifyRosters = True
      admin.save()
  for superUser in superUsers:
      course.courseAdmins.add(superUser)
  course.save()
  print("Created course %i" % i)

  for oldSection in oldCourse['sections']:
    section = Section.objects.create(name=oldSection['name'], course=course)
    for student in oldSection['students']:
      section.students.add(User.objects.get(email=student))
    for grader in oldSection['leaders']:
      section.leaders.add(User.objects.get(email=grader))
    section.save()

  print("Created sections for course %i" % i)

  for oldAssignment in oldCourse['assignments']:
    assignment = Assignment.objects.create(name=oldAssignment['name'], course=course, points=oldAssignment['points'], isReleased=oldAssignment['isReleased'])

    # Create rubric
    for category in oldAssignment['rubricCategories']:
      rubricCategory = RubricCategory.objects.create(name=category['name'], pointLimit=category['pointLimit'], assignment=assignment)
      for comment in category['rubricComments']:
        rubricComment = RubricComment.objects.create(text=comment['text'], pointDelta=comment['pointDelta'], category=rubricCategory)

    # Create submissions
    for oldSub in oldAssignment['submissions']:
      sub = Submission.objects.create(assignment=assignment)
      sub.grade = oldSub['grade']
      sub.isFinalized = oldSub['isFinalized']
      sub.date_finalized = oldSub['date_finalized']
      if oldSub['grader']:
        sub.grader = User.objects.get(email=oldSub['grader'])
      for student in oldSub['students']:
        sub.students.add(User.objects.get(email=student))

      sub.save()

      # Create files
      for oldFile in oldSub['files']:
        file = File.objects.create(submission=sub, code=oldFile['code'], name=oldFile['name'], extension=oldFile['extension'])
        oldComments = oldFile['comments']
        for oldComment in oldComments:
          rubricComments = RubricComment.objects.filter(category__assignment=assignment, text=oldComment['text'])
          if len(rubricComments) > 0:
            rubricComment = rubricComments[0]
            text = ''
            deduction = None
          else:
            text = oldComment['text']
            deduction = oldComment['pointDelta']
            rubricComment = None

          startLine = oldComment['startLine']
          endLine = oldComment['endLine']
          startChar = oldComment['startChar']
          endChar = oldComment['endChar']
          author = User.objects.get(email=oldSub['grader']) if oldSub['grader'] else course.courseAdmins.all()[0]
          comment = Comment.objects.create(rubricComment=rubricComment, text=text, pointDelta=deduction, file=file, startChar=startChar, endChar=endChar, startLine=startLine, endLine=endLine, author=author)

  print("Created assignments for course %i" % i)
  i = i + 1