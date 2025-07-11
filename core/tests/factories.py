from django.contrib.auth.models import User
from core.models import *

from django.db.models.signals import post_save
import factory

DEFAULT_COURSE_NAME = 'cs101'
DEFAULT_COURSE_PERIOD = 'f2020'
DEFAULT_ORG_NAME = 'School'


class OrganizationFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = Organization
    django_get_or_create = ('shortname',)

  name = DEFAULT_ORG_NAME
  shortname = factory.LazyAttribute(lambda o: o.name.lower())


@factory.django.mute_signals(post_save)
class ProfileFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = Profile
    # django_get_or_create = ('..user.username',)

  organization = factory.SelfAttribute('..organization')


@factory.django.mute_signals(post_save)
class AdminProfileFactory(ProfileFactory):
  canCreateCourses = True
  canModifyRosters = True
  organization = factory.SelfAttribute('..organization')


@factory.django.mute_signals(post_save)
class UserFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = User
    django_get_or_create = ('username',)

  username = factory.LazyAttribute(lambda o: "{}_{}{}@{}.edu".format(
      o.role, o.course, "_{}".format(o.count) if o.count is not None else '', o.organization.shortname))
  email = factory.SelfAttribute('username')
  password = 'rootabega'

  profile = factory.RelatedFactory(ProfileFactory, 'user')

  class Params:
    admin = factory.Trait(
        profile=factory.RelatedFactory(AdminProfileFactory, 'user')
    )
    role = factory.Maybe('admin', 'admin', 'user')

    course = DEFAULT_COURSE_NAME
    organization = factory.SubFactory(OrganizationFactory)

    count = None


@factory.django.mute_signals(post_save)
class AdminFactory(UserFactory):
  admin = True


@factory.django.mute_signals(post_save)
class SupergraderFactory(UserFactory):
  admin = False

  class Params:
    role = 'supergrader'


@factory.django.mute_signals(post_save)
class GraderFactory(UserFactory):
  admin = False

  class Params:
    role = 'grader'


@factory.django.mute_signals(post_save)
class StudentFactory(UserFactory):
  admin = False

  class Params:
    role = 'student'


@factory.django.mute_signals(post_save)
class CommentFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = Comment

  text = "new comment"
  pointDelta = 2
  author = factory.SubFactory(GraderFactory)
  file = factory.SubFactory('core.tests.factories.user.FileFactory')
  startLine = 0
  endLine = 0
  startChar = 1
  endChar = 4


@factory.django.mute_signals(post_save)
class FileFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = File

  name = "hello.java"
  extension = ".java"
  code = """public class LoopUtils {

  // Find the max element of an array
  public static int max(int[] arr) {

  }
}"""
  submission = factory.SubFactory('core.tests.factories.user.SubmissionFactory')


@factory.django.mute_signals(post_save)
class SubmissionFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = Submission

  assignment = factory.SubFactory('core.tests.factories.user.AssignmentFactory')
  files = factory.RelatedFactory(FileFactory, 'submission')


@factory.django.mute_signals(post_save)
class SectionFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = Section

  name = "P01"
  course = factory.SubFactory('core.tests.factories.user.CourseFactory')


@factory.django.mute_signals(post_save)
class RubricCommentFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = RubricComment

  text = "Missing a semicolon"
  pointDelta = 1
  category = factory.SubFactory('core.tests.factories.user.RubricCategoryFactory')


@factory.django.mute_signals(post_save)
class RubricCategoryFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = RubricCategory

  name = "General"
  assignment = factory.SubFactory('core.tests.factories.user.AssignmentFactory')
  rubricComments = factory.RelatedFactory(RubricCommentFactory, 'category')


@factory.django.mute_signals(post_save)
class AssignmentFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = Assignment
    django_get_or_create = ('name', 'course')

  name = 'Hello World'
  points = 20
  isReleased = False
  course = factory.SubFactory('core.tests.factories.user.CourseFactory')

  submissions = factory.RelatedFactory(SubmissionFactory, 'assignment')
  rubricCategories = factory.RelatedFactory(RubricCategoryFactory, 'assignment')


@factory.django.mute_signals(post_save)
class CourseFactory(factory.django.DjangoModelFactory):

  class Meta:
    model = Course
    django_get_or_create = ('name', 'period', 'organization')

  name = "cs101"
  period = "s2020"
  organization = factory.SubFactory(OrganizationFactory)
  sections = factory.RelatedFactory(SectionFactory, 'course')

  @factory.post_generation
  def courseAdmins(self, create, extracted, **kwargs):
    for i in range(2):
      self.courseAdmins.add(AdminFactory(course=self.name, organization=self.organization, count=i))
    for i in range(2, 4):
      self.inactive_courseAdmins.add(AdminFactory(course=self.name, organization=self.organization, count=i))

  @factory.post_generation
  def graders(self, create, extracted, **kwargs):
    for i in range(2):
      self.graders.add(GraderFactory(course=self.name, organization=self.organization, count=i))
    for i in range(2, 4):
      self.inactive_graders.add(GraderFactory(course=self.name, organization=self.organization, count=i))

  @factory.post_generation
  def students(self, create, extracted, **kwargs):
    for i in range(2):
      self.students.add(StudentFactory(course=self.name, organization=self.organization, count=i))
    for i in range(2, 4):
      self.inactive_students.add(StudentFactory(course=self.name, organization=self.organization, count=i))

  @factory.post_generation
  def superGraders(self, create, extracted, **kwargs):
    for i in range(2):
      sg = SupergraderFactory(course=self.name, organization=self.organization, count=i)
      self.superGraders.add(sg)
      self.graders.add(sg)

  @factory.post_generation
  def assignments(self, create, extracted, **kwargs):
    a1 = AssignmentFactory(course=self, name="Loops")
    self.assignments.add(a1)
    f = a1.submissions.first().files.first()
    f.comments.add(CommentFactory(author=a1.course.courseAdmins.first(), file=f))
    f.save()
