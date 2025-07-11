from django.contrib.auth.models import User
from core.models import Profile
from core.models import Organization, Course
from core.models import Section, Assignment
from core.models import Submission, File, Comment
from core.models import RubricCategory, RubricComment
import random

# Create an organization, course, and assignment
princeton = Organization.objects.create(
    name="Princeton University", shortname="Princeton")
cos126s2019 = Course.objects.create(
    organization=princeton, period="S2019", name="COS126")

assignments = []
hellos2019 = Assignment.objects.create(
    course=cos126s2019, points=20, isReleased=True, name="Hello")
assignments.append(hellos2019)
loopss2019 = Assignment.objects.create(
    course=cos126s2019, points=20, isReleased=True, name="loops")
assignments.append(loopss2019)
nbodys2019 = Assignment.objects.create(
    course=cos126s2019, points=20, isReleased=True, name="nbody")
assignments.append(nbodys2019)
sierpinskis2019 = Assignment.objects.create(
    course=cos126s2019, points=20, isReleased=True, name="sierpinski")
assignments.append(sierpinskis2019)
hammings2019 = Assignment.objects.create(
    course=cos126s2019, points=20, isReleased=True, name="hamming")
assignments.append(hammings2019)
lfsrs2019 = Assignment.objects.create(
    course=cos126s2019, points=20, isReleased=True, name="lfsr")
assignments.append(lfsrs2019)
guitars2019 = Assignment.objects.create(
    course=cos126s2019, points=20, isReleased=True, name="guitar")
assignments.append(guitars2019)
markovs2019 = Assignment.objects.create(
    course=cos126s2019, points=20, isReleased=True, name="markov")
assignments.append(markovs2019)

# Create some superusers
admin = User.objects.create(
    username='admin@codepost.io', email='admin@codepost.io', password="rootabega")
superadmin = User.objects.create(
    username='superadmin@codepost.io', email='superadmin@codepost.io', password="rootabega")
superadmin.profile.organization = princeton
admin.profile.organization = princeton
admin.profile.canCreateCourses = True
superadmin.profile.canCreateCourses = True
admin.profile.canModifyRosters = True
superadmin.profile.canModifyRosters = True
admin.set_password("rootabega")
admin.save()
superadmin.is_superuser = True
superadmin.is_staff = True
superadmin.save()

# Add some graders to the course
cos126s2019.graders.add(admin)
cos126s2019.graders.add(superadmin)
cos126s2019.save()

# Add some courseadmins to the course
cos126s2019.courseAdmins.add(admin)
cos126s2019.courseAdmins.add(superadmin)
cos126s2019.save()

section1 = Section.objects.create(name="P01", course=cos126s2019)
section1.leaders.add(admin)
section1.save()

code = "<div> simple code </div>\n<div className=style> another simple code </div>"


# Create some students and add them to the course
for i in range(0, 20):
    username = "student" + str(i) + "@princeton.edu"
    tmpUser = User.objects.create(
        username=username, email=username, password="rootabega")
    tmpUser.set_password("rootabega")
    cos126s2019.students.add(tmpUser)
    tmpUser.save()
    cos126s2019.save()
    section1.students.add(tmpUser)
    section1.save()
    if i < 15:
        for assn in assignments:
            sub = Submission.objects.create(assignment=assn)
            sub.students.add(tmpUser)
            code = code
            tmpFile = File.objects.create(
                name="hello.java", code=code, submission=sub, extension='java')
            Comment.objects.create(text="good job, " + username, author=superadmin,
                                   file=tmpFile, startChar=1, endChar=4, startLine=1, endLine=1)
            sub.isFinalized = True
            sub.grade = random.randint(0, 20)
            if i != 12:
                sub.grader = superadmin
            sub.save()

username = 'partner1@princeton.edu'
tmpUser = User.objects.create(
    username=username, email=username, password="rootabega")
tmpUser.set_password("rootabega")
cos126s2019.students.add(tmpUser)
tmpUser.save()

username = 'partner2@princeton.edu'
tmpUser2 = User.objects.create(
    username=username, email=username, password="rootabega")
tmpUser2.set_password("rootabega")
cos126s2019.students.add(tmpUser2)
tmpUser2.save()
cos126s2019.save()

username = 'partner3@princeton.edu'
tmpUser3 = User.objects.create(
    username=username, email=username, password="rootabega")
tmpUser3.set_password("rootabega")
cos126s2019.students.add(tmpUser3)
tmpUser3.save()

username = 'partner4@princeton.edu'
tmpUser4 = User.objects.create(
    username=username, email=username, password="rootabega")
tmpUser4.set_password("rootabega")
cos126s2019.students.add(tmpUser4)
tmpUser4.save()
cos126s2019.save()

username = 'partner5@princeton.edu'
tmpUser5 = User.objects.create(
    username=username, email=username, password="rootabega")
tmpUser5.set_password("rootabega")
cos126s2019.students.add(tmpUser5)
tmpUser5.save()

username = 'partner6@princeton.edu'
tmpUser6 = User.objects.create(
    username=username, email=username, password="rootabega")
tmpUser6.set_password("rootabega")
cos126s2019.students.add(tmpUser6)
tmpUser6.save()
cos126s2019.save()

for assn in assignments:
    sub = Submission.objects.create(assignment=assn)
    sub.students.add(tmpUser)
    sub.students.add(tmpUser2)
    code = code
    tmpFile = File.objects.create(
        name="hello.java", code=code, submission=sub, extension='java')
    Comment.objects.create(text="good job", author=superadmin,
                           file=tmpFile, startChar=1, endChar=4, startLine=1, endLine=1)
    sub.isFinalized = True
    sub.grade = random.randint(0, 20)
    sub.grader = superadmin
    section1.students.add(tmpUser)
    section1.students.add(tmpUser2)
    section1.save()
    sub.save()

for assn in assignments:
    sub = Submission.objects.create(assignment=assn)
    sub.students.add(tmpUser3)
    sub.students.add(tmpUser4)
    code = code
    tmpFile = File.objects.create(
        name="hello.java", code=code, submission=sub, extension='java')
    Comment.objects.create(text="good job", author=superadmin,
                           file=tmpFile, startChar=1, endChar=4, startLine=1, endLine=1)
    sub.isFinalized = True
    sub.grade = random.randint(0, 20)
    sub.grader = superadmin
    section1.students.add(tmpUser3)
    section1.students.add(tmpUser4)
    section1.save()
    sub.save()

for assn in assignments:
    sub = Submission.objects.create(assignment=assn)
    sub.students.add(tmpUser5)
    sub.students.add(tmpUser6)
    code = code
    tmpFile = File.objects.create(
        name="hello.java", code=code, submission=sub, extension='java')
    Comment.objects.create(text="good job", author=superadmin,
                           file=tmpFile, startChar=1, endChar=4, startLine=1, endLine=1)
    sub.isFinalized = False
    sub.grade = random.randint(0, 20)
    section1.students.add(tmpUser5)
    section1.students.add(tmpUser6)
    section1.save()
    sub.save()

for i in range(0, 2):
    name = "general" + str(i)
    rubricCategory = RubricCategory.objects.create(
        assignment=hellos2019, name=name, pointLimit=10)
    rubricComment1 = RubricComment.objects.create(
        text='Missing a semicolon', pointDelta=2, category=rubricCategory)
    rubricComment2 = RubricComment.objects.create(
        text='Need more comments', pointDelta=3, category=rubricCategory)
    rubricComment3 = RubricComment.objects.create(
        text='Need more comments1', pointDelta=3, category=rubricCategory)
    rubricComment4 = RubricComment.objects.create(
        text='Need more comments2', pointDelta=3, category=rubricCategory)
    rubricComment5 = RubricComment.objects.create(
        text='Need more comments3', pointDelta=3, category=rubricCategory)

    name2 = "algos" + str(i)
    rubricCategory2 = RubricCategory.objects.create(
        assignment=hellos2019, name=name2, pointLimit=20)
    rubricComment1 = RubricComment.objects.create(
        text='Missing a semicolon', pointDelta=2, category=rubricCategory2)
    rubricComment2 = RubricComment.objects.create(
        text='Need more comments', pointDelta=3, category=rubricCategory2)
    rubricComment3 = RubricComment.objects.create(
        text='Need more comments2', pointDelta=3, category=rubricCategory2)
    rubricComment4 = RubricComment.objects.create(
        text='Need more comments4', pointDelta=3, category=rubricCategory2)
    rubricComment5 = RubricComment.objects.create(
        text='Need more comments5', pointDelta=3, category=rubricCategory2)

users = User.objects.all()
for user in users:
    user.profile.organization = princeton
    user.save()
