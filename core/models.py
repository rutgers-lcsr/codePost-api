import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Avg
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils.timezone import now
from jsonfield import JSONField
from rest_framework.authtoken.models import Token

from core.validators import validate_hex_color

# Notes
# Consider using indexes (db_index) to speed up common queries
# (https://stackoverflow.com/questions/14786413/add-indexes-db-index-true)

class BaseModel(models.Model):
  created = models.DateTimeField(editable=False, default=now)
  modified = models.DateTimeField(default=now)

  class Meta:
    abstract = True

  def save(self, *args, **kwargs):
    if self.pk:
      ''' Update '''

      ######################################################################
      # Check which fields have been updated
      ######################################################################
      cls = self.__class__
      old = cls.objects.get(pk=self.pk)
      new = self
      changed_fields = []
      for field in cls._meta.get_fields():
        field_name = field.name
        try:
          if getattr(old, field_name) != getattr(new, field_name):
            changed_fields.append(field_name)
        except Exception:
          pass
      kwargs['update_fields'] = changed_fields
      ######################################################################
      ######################################################################
    else:
      ''' Create '''
      self.created = now()

    self.modified = now()
    return super(BaseModel, self).save(*args, **kwargs)

############# User Section ####################################################

# Internal Model - not published in public API


class Organization(BaseModel):
  name = models.CharField(max_length=64, unique=True,
                          help_text=("The name of the organization."))
  shortname = models.CharField(max_length=12, unique=True, help_text=(
      "A shortname for the organization (e.g. Princeton University -> PU)"))

  class Meta:
    ordering = ('name',)

  def __str__(self):
    return self.shortname


# Internal Model - not published in public API
# https://wsvincent.com/django-custom-user-model-tutorial/


class Profile(BaseModel):
  user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile", help_text=(
      "The username of the related user."))
  api_token = models.ForeignKey(
      Token, on_delete=models.SET_NULL, blank=True, null=True)
  organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True,
                                   null=True, related_name="profiles", help_text=("The related organization_id"))
  canCreateCourses = models.BooleanField(default=False)
  canModifyRosters = models.BooleanField(default=False)
  pendingValidation = models.BooleanField(default=False)
  showProductTips = models.BooleanField(default=True)
  isPasswordSet = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, the user has set a password for their account. If False, the user has not set a password and should be prompted to do so."))

  stripeCustomerId = models.CharField(max_length=96, unique=True, null=True, blank=True, help_text=(
      "The customer_id from the Stripe customer object."))

  def __str__(self):
    return self.user.email



class Course(BaseModel):
  name = models.CharField(max_length=36, help_text=("The name of the course."))
  organization = models.ForeignKey(Organization, on_delete=models.CASCADE,
                                   related_name="courses", help_text=("The related organization_id"))
  period = models.CharField(max_length=32, help_text=(
      "A string describing the period (e.g. F2019, T32019, etc."))
  archived = models.BooleanField(default=False, help_text=("If True, the course will not be editable."))

  students = models.ManyToManyField(User, related_name="student_courses", help_text=(
      "A list of usernames of students enrolled in the course."))
  inactive_students = models.ManyToManyField(
      User,
      related_name="student_inactive_courses",
      help_text=("A list of usernames of students unenrolled in the course."),
      blank=True,
      default=list
  )
  inactive_graders = models.ManyToManyField(
    User, 
    related_name="grader_inactive_courses", 
    help_text=(
      "A list of usernames of graders inactive in the course."),
    blank=True,
    default=list
    )
  inactive_courseAdmins = models.ManyToManyField(
    User, 
    related_name="courseAdmin_inactive_courses", 
    help_text=(
      "A list of usernames of admins inactive in the course."),
    blank=True,
    default=list
  )
  graders = models.ManyToManyField(User, related_name="grader_courses", help_text=(
      "A list of usernames of graders for the course."))
  superGraders = models.ManyToManyField(User, related_name="superGrader_courses", help_text=(
      "A list of usernames of graders for the course who have expanded permissions."))
  courseAdmins = models.ManyToManyField(User, related_name="courseAdmin_courses", help_text=(
      "A list of usernames for admins for the course."))

  # Settings
  sendReleasedSubmissionsToBack = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, submissions that are claimed and subsequently released will be added to the back of the grading queue."))
  showStudentsStatistics = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, students will be able to view basic grade statistics for released assignments."))
  timezone = models.CharField(default="US/Eastern", max_length=32, help_text=("Timezone in which course operates."))
  emailNewUsers = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, when emails are added to a course roster that do not correspond to existing codePost users, those emails will be sent an email notifying that they have been added to a course and providing a link to register their (new) accounts."))
  anonymousGradingDefault = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, new assignments will have anonymous grading mode enabled by default."))

  allowGradersToEditRubric = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, graders will be allowed to add and update unlinked rubric comments."))
  minComments = models.IntegerField(default=0, help_text=(
      "An integer representing the minimum number of comments that graders are asked to make prior to finalizing. 0 indicates no minimum."))
  noUnfinalize = models.BooleanField(default=False, help_text=(
      "If True, only admins can unfinalize submissions."))
  lateDayCreditsAllowable = models.IntegerField(blank=True, null=True, help_text=(
      "The number of Late Day Credits that each student gets at the beginning of the term. Null if the course does not have students submit directly to codePost."))
  rosterMap = JSONField(default={}, help_text="An map of LMS id to codePost student emails for this course.", blank=True)
  studentCaptions = JSONField(default={}, help_text="Map student emails to captions.", blank=True)
  useStudentCaptions = models.BooleanField(default=False, help_text=(
      "If True, graders will see student captions (where defined) instead of emails."))
  activateQueue = models.BooleanField(default=True, help_text=(
      "If True, will be able to claim submissions from the ungraded queue."))
  inviteCode = models.CharField(max_length=10, help_text=("A token which allows students to join course."), null=True, blank=True, unique=True)

  course = property(lambda self: self)

  emailWhitelist = models.TextField(blank=True, help_text=("Permissible student email domains."))
  inviteCodeEnabled = models.BooleanField(default=False, help_text=("If True, the course's invite code can be used."))
  enableStudentFeedbackNotifications = models.BooleanField(default=False, help_text=("If True, the graders may send students feedback notifications."))

  def validate_manual_payments(value):
    if not isinstance(value, list):
        raise ValidationError('Must be an array')
    
    for item in value:
        if not set(['id', 'timestamp', 'amount', 'description', 'email']).issubset(item.keys()):
            raise ValidationError('Each manual payment must have an id, timestamp, amount, description, and email field')
        
  manual_payments = JSONField(default=list, help_text="An array of manual payments", validators=[validate_manual_payments], blank=True)
  waiver_requested = models.BooleanField(default=False, help_text=("If True, the course has requested a waiver."))

  class Meta:
    unique_together = ('name', 'period', 'organization')
    ordering = ('name', 'period')

  def __str__(self):
    return str(self.name) + " | " + self.period


##########################################################################

############# Course Infrastructure Section ##############################


class Section(BaseModel):
  name = models.CharField(
      max_length=16, help_text=("The name of the section."))
  course = models.ForeignKey(Course, on_delete=models.CASCADE,
                             related_name='sections', help_text=("The related course_id."))
  leaders = models.ManyToManyField(User, blank=True, related_name='leader_sections', help_text=(
      "A list of usernames of graders leading the section."))
  students = models.ManyToManyField(User, related_name='student_sections', help_text=(
      "A list of usernames of students in the section."))

  class Meta:
    unique_together = ('name', 'course')
    ordering = ('name',)

  def __str__(self):
    return self.name + " | " + str(self.course)


class Assignment(BaseModel):
  isVisible = models.BooleanField(default=True, help_text=(
      "A boolean field. 'True' if the assignment is viewable by students."))

  explanation = models.TextField(blank=True, help_text=("The explanation of an assignment, visible to students."))
  hideFrom = models.ManyToManyField(Section, related_name="hidden_sections", help_text=("Sections from which to hide this assignment."), blank=True)

  course = models.ForeignKey(Course, on_delete=models.CASCADE,
                             related_name='assignments', help_text=("The related course_id."))
  name = models.CharField(
      max_length=32, help_text=("The name of the assignment."))
  isReleased = models.BooleanField(default=False, help_text=(
      "A boolean field. 'True' if the assignment is released for students to view. 'False' otherwise."))
  points = models.DecimalField(validators=[MinValueValidator(0.0)], max_digits=5,
                               decimal_places=2, help_text=("Total points for the assignment."))
  mean = models.DecimalField(validators=[MinValueValidator(0.0)], max_digits=5, decimal_places=2, blank=True, null=True, help_text=(
      "The average grade of the assignment. Null if no submissions yet"))
  median = models.DecimalField(validators=[MinValueValidator(0.0)], max_digits=5, decimal_places=2, blank=True, null=True, help_text=(
      "The median grade of the assignment. Null if no submissions yet"))
  sortKey = models.IntegerField(default=0, help_text=(
      "Optional integer to specify the order of a Course's Assignments."))

  # Settings
  hideGrades = models.BooleanField(default=False, help_text=(
      "A boolean field. 'True' if the students should not see their grades for this assignment. 'False' otherwise."))
  anonymousGrading = models.BooleanField(default=False, help_text=(
      "A boolean field. If 'True', graders will not have access to the students field of submission objects, unless they have elevated privileges."))
  commentFeedback = models.BooleanField(default=True, help_text=(
      "A boolean field. If True, students can provide feedback on rubric comments."))
  allowStudentUpload = models.BooleanField(default=False, help_text=(
      "A boolean field. If true, students will be allowed to upload submissions until the upload due date."))
  allowStudentUploadWithPartners = models.BooleanField(default=False, help_text=("A boolean field. If true, students will be allowed to invite partners to their submission."))
  uploadDueDate = models.DateTimeField(null=True, help_text=(
      "The date after which students are not allowed to upload submissions. Only useful if allowStudentUplaod is set to True."))
  liveFeedbackMode = models.BooleanField(default=False, help_text=(
      "A boolean field. If true, students can see their submission and comments before finalization and published"))
  additiveGrading = models.BooleanField(default=False, help_text=(
      "A boolean field. If true, grades begin at 0 (instead of assignment.points)"))
  hideGradersFromStudents = models.BooleanField(default=True, help_text=(
      "A boolean field. If True, the graders of a submission will be hidden from students."))
  collaborativeRubricMode = models.BooleanField(default=False, help_text=(
      "A boolean field. If true, admins and graders can edit the assignment rubric inline in the code console."))

  allowRegradeRequests = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, students will be allowed to submit questions and regrade requests after their submission has been graded."))
  regradeInstructions = models.TextField(default='', blank=True, help_text=(
      "Instructions (in Markdown) to show students when they submit regrade requests."))
  regradeDeadline = models.DateTimeField(null=True, help_text=(
      "The date after which students are not allowed submit a regrade request."))

  forcedRubricMode = models.BooleanField(default=False, help_text=(
      "A boolean field. If true, graders will be required to link a rubric comment on all comments."))
  templateMode = models.BooleanField(
      default=False, help_text="A boolean field. If true, admins will be able upload template code files. Those template files will be used to de-emphasize provided versus student-written code in submissions.")
  showFrequentlyUsedRubricComments = models.BooleanField(
      default=False, help_text="A boolean field. If true, an assignment's 10 most frequently used rubric comments will be shown within the code console.")

  allowLateUploads = models.BooleanField(default=False, help_text=(
      "A boolean field. If True and an uploadDueDate is set, students will still be able to submit after a deadline has passed."))
  lateDeductions = JSONField(default=[], help_text="An array of point deductions for each day late.")

  def __str__(self):
    return str(self.name) + " | " + str(self.course)

  def calculate_average_and_median(self):
    finalizedSubmissions = self.submissions.filter(isFinalized=True)
    if (len(finalizedSubmissions) == 0):
      return (None, None)

    scores = finalizedSubmissions.values_list(
        'grade', flat=True).order_by('grade')
    mean = scores.aggregate(Avg('grade'))['grade__avg']
    median = scores[int(round(len(scores) / 2))]
    return (mean, median)

  def save(self, *args, **kwargs):
    ''' Calculate mean, median on save '''
    is_new = self.pk is None
    super(Assignment, self).save(*args, **kwargs)
    
    if is_new:
        # Now self.pk is available
        self.mean, self.median = self.calculate_average_and_median()
        super().save(update_fields=["mean", "median"])


  class Meta:
    unique_together = ('name', 'course')
    ordering = ('sortKey', 'name')
    


class RubricCategory(BaseModel):
  assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,
                                 related_name="rubricCategories", help_text=("The related assignment_id."))
  name = models.CharField(max_length=72, help_text=(
      "The name of the category (e.g. 'General')."))
  pointLimit = models.IntegerField(blank=True, null=True, help_text=(
      "An integer cap for the maximum number of points that can be deducted under this category."))
  sortKey = models.IntegerField(default=0, help_text=(
      "Optional integer to specify the order of an Assignment's Rubric Categories"))
  helpText = models.TextField(
      blank=True, help_text=("Subtext for the category name."))
  atMostOnce = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, at most one rubric comment from this rubric category can be applied to a submission."))

  course = property(lambda self: self.assignment.course)



class RubricComment(BaseModel):
  text = models.TextField(blank=True, help_text=("The text on the rubric comment."))
  explanation = models.TextField(blank=True, help_text=("The explanation of a rubric comment shown to students."))
  instructionText = models.TextField(blank=True, help_text=(
      "Text shown to the grader in the custom text field of an instance comment."))
  templateTextOn = models.BooleanField(default=False, help_text=(
      "If True, instruction text will pre-populate instance comments."))
  pointDelta = models.DecimalField(max_digits=5, decimal_places=2, help_text=(
      "The points deducted. A negative number represents a bonus."))
  category = models.ForeignKey(RubricCategory, on_delete=models.CASCADE,
                               related_name="rubricComments", help_text=("The related rubricCategory_id"))
  sortKey = models.IntegerField(default=0, help_text=(
      "Optional integer to specify the order of a Rubric Category's comments."))
  name = models.CharField(max_length=255, null=True, blank=True)


  course = property(lambda self: self.category.course)


###############################################################################


############# Submissions Section #############################################

class Submission(BaseModel):
  assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,
                                 related_name="submissions", help_text=("The related assignment_id."))
  students = models.ManyToManyField(User, related_name="student_submissions", help_text=(
      "A list of usernames of students for the submission."))
  grader = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL, related_name="grader_submissions", help_text=(
      "The username of the assigned grader for the submission."))
  isFinalized = models.BooleanField(default=False, help_text=(
      "A boolean field. 'True' if the submission is finalized. 'False' otherwise."))
  dateEdited = models.DateTimeField(default=now, help_text=(
      "The date this submission (or any of its associated files or comments) was last edited."))
  grade = models.DecimalField(validators=[MinValueValidator(0.0)], max_digits=5, decimal_places=2,
                              blank=True, null=True, help_text=("The grade for the submission. Null if not graded yet."))
  queueOrderKey = models.IntegerField(default=0, help_text=(
      "Index used to order the queue from which graders draw submissions. Will sort low to high."))
  gradeFrozen = models.BooleanField(default=False, help_text=(
      "A boolean field. If 'True', the submissions grade will not be re-calculated based on the current comments applied to it. Warning: this can cause grade to become out of sync with the submission's comments."))
  dateUploaded = models.DateTimeField(
      default=now, help_text=("The date this submission was created."))

  lateDayCreditsUsed = models.IntegerField(default=0, help_text=(
      "The number of Late Day Credits used by the Submission."))

  # Student question
  questionIsOpen = models.BooleanField(default=False, help_text=(
      "A boolean field. If true the submission has an open question."))
  questionIsRegrade = models.BooleanField(default=False, help_text=(
      "A boolean field. If 'True', the submission's question is a regrade request."))
  questionResponder = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL,
                                        related_name="grader_regraded_submissions", help_text=("The username of the responder for the question."))
  questionText = models.CharField(
      blank=True, max_length=500, help_text=("The text of the question."))
  questionResponse = models.TextField(blank=True, help_text=("The text of the question response."))
  questionDate = models.DateTimeField(null=True, blank=True, help_text=(
      "The date the request / question was submitted."))
  responseDate = models.DateTimeField(
      null=True, blank=True, help_text=("The date the response was submitted."))
  testRunsCompleted = models.PositiveIntegerField(default=0, help_text=(
      "Number of times exposed tests have been run for a submission. It only increments if the maxStudentTestRuns Environment setting is on."))

  course = property(lambda self: self.assignment.course)

  def save(self, *args, **kwargs):
    if not self.gradeFrozen and self.isFinalized:
      self.grade = calculate_grade(self)
    self.dateEdited = now()


    super(Submission, self).save(*args, **kwargs)
  class Meta:
    ordering = ('queueOrderKey', 'dateUploaded')

class FileTemplate(BaseModel):
  name = models.CharField(max_length=150, help_text=("The name of the template file."))
  code = models.TextField(blank=True, help_text=("The code in a file."))
  extension = models.CharField(max_length=36, help_text=(
      "The extension for the file (e.g. '.java' or '.py'"))
  path = models.CharField(null=True, blank=True, max_length=500, help_text=(
      "Optional file path, delimited by slashes, to indicate a directory structure in submission."))
  assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,
                                 related_name="fileTemplates", help_text=("The related assignment_id."))
  required = models.BooleanField(
      default=False, help_text="If student upload is enabled, a file with this name and extension will be required.")
  description = models.TextField(blank=True, help_text=("Optional description shown to students."))

  course = property(lambda self: self.assignment.course)

  def save(self, *args, **kwargs):
    if '\r\n' in self.code:
      self.code = self.code.replace("\r\n", "\n")

    return super(FileTemplate, self).save(*args, **kwargs)


class File(BaseModel):
  name = models.CharField(max_length=150, help_text=("The name of the file."))
  code = models.TextField(help_text=("The code in a file."))
  submission = models.ForeignKey(Submission, on_delete=models.CASCADE,
                                 related_name="files", help_text=("The related submission_id."))
  extension = models.CharField(max_length=36, help_text=(
      "The extension for the file (e.g. '.java' or '.py'"))
  path = models.CharField(null=True, blank=True, max_length=500, help_text=(
      "Optional file path, delimited by slashes, to indicate a directory structure in submission."))
  hiddenBeforePublish = models.BooleanField(default=False, help_text=(
      "Whether this file should hidden to students before their feedback has been published. This is for autogenerated test files that shouldn't be exposed to students on upload."))

  course = property(lambda self: self.submission.course)

  def save(self, *args, **kwargs):
    if '\r\n' in self.code:
      self.code = self.code.replace("\r\n", "\n")

    return super(File, self).save(*args, **kwargs)


class CommentTag(BaseModel):
  label = models.CharField(max_length=64, unique=True, help_text=("The tag label."))

  # FIXME: Only for internal checking, should also create serializer field
  def save(self, *args, **kwargs):
    self.label = self.label.lower().strip()

    super(CommentTag, self).save(*args, **kwargs)


class Comment(BaseModel):
  text = models.TextField(blank=True, help_text=("The text on the comment"))
  pointDelta = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, help_text=(
      "The points deducted. A negative number represents a bonus."))
  rubricComment = models.ForeignKey(RubricComment, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="comments", help_text=("The related rubricComment_id. Null if no rubric comment linked."))
  author = models.ForeignKey(User, on_delete=models.CASCADE, help_text=(
      "The username of the author of the comment."))
  file = models.ForeignKey(File, on_delete=models.CASCADE,
                           related_name="comments", help_text=("The related file_id."))
  startChar = models.IntegerField(help_text=(
      "An integer representing the character position a comment begins on."))
  endChar = models.IntegerField(help_text=(
      "An integer representing the character position a comment ends on."))
  startLine = models.IntegerField(help_text=(
      "An integer representing the line number a comment begins on."))
  endLine = models.IntegerField(help_text=(
      "An integer representing the line number a comment begins on."))
  feedback = models.IntegerField(default=0, help_text=(
      "An integer representing the feedback applied to this comment. Currently only valid if rubricComment is not null."))
  color = models.CharField(max_length=7, blank=True, null=True, help_text=(
      "The color in which the comment will render in codePost."), validators=[validate_hex_color])
  tags = models.ManyToManyField(CommentTag, related_name="tag_comments",
                                help_text=("A list of tags (strings) for the comment."))

  course = property(lambda self: self.file.course)

  def save(self, *args, **kwargs):
    if self.rubricComment:
      self.pointDelta = None

    super(Comment, self).save(*args, **kwargs)


############################## Autograder #####################################################

class TestCategory(BaseModel):
  assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,
                                 related_name="testCategories", help_text=("The related assignment__id."))
  name = models.CharField(max_length=48, help_text=("The name of the test."))
  course = property(lambda self: self.assignment.course)

  class Meta:
    unique_together = ('name', 'assignment')

testTypes = (
    ('io', 'io'),
    ('io_cli', 'io_cli'),
    ('unit', 'unit'),
    ('shell', 'shell'),
    ('file', 'file'),
    ('external', 'external'),)

testCase_status_types = (
    (0, 'Passed'),
    (1, 'Failed'),
    (2, 'Error'),
    (3, 'Never run'),
)


class TestCase(BaseModel):
  testCategory = models.ForeignKey(TestCategory, on_delete=models.CASCADE,
                                   related_name="testCases", help_text=("The related testCategory__id."))
  sortKey = models.IntegerField(default=0, help_text=(
      "Integer to specify the order of a Assignment's Tests."))
  description = models.CharField(max_length=48, help_text=("Test description."))
  type = models.CharField(max_length=25, choices=testTypes)
  pointsFail = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text=(
      "The points assigned to a failed test."))
  pointsPass = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text=(
      "The points assigned to a passed test."))
  text = models.TextField(blank=True, help_text=("The text of the test"))
  explanation = models.TextField(blank=True, help_text=("A description of what the test achieves"))
  exposed = models.BooleanField(default=False, help_text=(
      "If True and type is not 'external', this test will be run when a student submits, and the results shown to the student"))
  lastSolutionRun = models.IntegerField(default=3, choices=testCase_status_types)

  ################# Only relevant to I/O Tests ########################################
  function = models.TextField(blank=True, help_text=("The function name to test"))
  fileName = models.TextField(blank=True, help_text=("The file name to test"))
  outputIsFile = models.BooleanField(default=False, help_text=(
      "A boolean field. 'True' if the output is the name of a file to be compared to."))
  expectedOutput = models.TextField(blank=True, help_text=("The expected output of the test"))
  input = models.TextField(blank=True, help_text=("The input of the test"))
  checkReturn = models.BooleanField(default=True, help_text=(
      "A boolean field. 'True' if the output should be compared to the return of the function. False if it should be compared to std out."))
  isFlexible = models.BooleanField(default=False, help_text=("Flexible mode for output checking."))
  outputIsRegexp = models.BooleanField(default=False, help_text=("Is expected output specified in the form of a regexp?"))

  course = property(lambda self: self.testCategory.course)


class SubmissionTest(BaseModel):
  submission = models.ForeignKey(Submission, on_delete=models.CASCADE,
                                 related_name="tests", help_text=("The related submission_id."))
  testCase = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name="instances",
                               help_text=("The related parent test id"))
  logs = models.TextField(help_text=("The logs of a test."))
  passed = models.BooleanField(help_text=(
      "A boolean field. 'True' if the submission passed this test. 'False' otherwise."))
  isError = models.BooleanField(default=False, help_text=(
      "A boolean field. 'True' if the test resulted in an error. False otherwise."))

  course = property(lambda self: self.submission.course)

  class Meta:
    ordering = ('created', )

################################################################################################
##################################### Internal Models ##########################################
################################################################################################


class SubmissionHistory(BaseModel):
  submission = models.ForeignKey(Submission, on_delete=models.CASCADE,
                                 related_name="histories", help_text=("The related submission_id."))
  student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="student_submissionHistories", help_text=(
      "Username of student for the submissionHistory"))
  hasViewed = models.BooleanField(default=False, help_text=(
      "A boolean field indicating whether the student has seen the submission."))
  dateViewed = models.DateTimeField(null=True, blank=True, help_text=(
      "The date this submission (or any of its associated files or comments) was last edited."))

  course = property(lambda self: self.submission.course)

  def save(self, *args, **kwargs):
    if self.hasViewed:
      self.dateViewed = now()
    super(SubmissionHistory, self).save(*args, **kwargs)

  class Meta:
    unique_together = ('submission', 'student')
    ordering = ['-created']

##################################### Autograder Models ##########################################


class Environment(BaseModel):
  assignment = models.OneToOneField(Assignment, on_delete=models.CASCADE,
                                    related_name="environment", help_text=("The related assignment__id."))
  dockerRunInstructions = JSONField(default=[], blank=True, help_text="Instructions to be added to the docker file with a RUN command.")
  language = models.CharField(max_length=25, choices=(
      ('python-3.7', 'python-3.7'),
      ('python-2.7', 'python-2.7'),
      ('java', 'java'),
      ('c/c++', 'c/c++'),
      ('javascript', 'javascript'),
      ('haskell', 'haskell'),
      ('ocaml', 'ocaml'),
      ('ruby', 'ruby'),
      ('php', 'php'),
      ('other', 'other')), default='python-3.7')
  buildType = models.CharField(max_length=25, choices=(
      ('default', 'default'),
      ('alpine', 'alpine'),
      ('ubuntu', 'ubuntu'),
      ('windows', 'windows')), default='default')
  dockerfile = models.TextField(default='', blank=True, help_text=(
      "A custom set of docker commands to append to the base image docker file"))
  compileText = models.TextField(default='', blank=True, help_text=(
      "Command to be run on every submission before tests"))
  isRunning = models.BooleanField(default=False, help_text=(
      "A boolean field indicating whether the environment currently is running all submissions with all tests."))
  dumpMode = models.BooleanField(default=False, help_text=(
      "A boolean field indicating whether all test outputs should be dumped to a _tests.txt file."))
  testParsing = models.BooleanField(default=True, help_text=(
      "A boolean field indicating whether tests should be parsed from sourcefiles on save."))
  allowNetworkAccess = models.BooleanField(default=False, help_text=(
      "A boolean field indicating whether tests should be run in a container that allows network access."))
  maxStudentTestRuns = models.PositiveIntegerField(null=True, blank=True, help_text=(
      "An integer field indicating the max times that tests will be run if tests are exposed."))
  exposeDumpLogs = models.BooleanField(default=False, help_text=(
      "If dumpMode is turned on, this boolean field determins whether the tests.txt is exposed to students on submit."))
  maxExposedFailedTests = models.PositiveIntegerField(null=True, blank=True, help_text=(
      "An integer field indicating the limit of the number of failed tests that will be exposed to a student (nudge mode)."))
  buildID = models.PositiveIntegerField(default=0, help_text=(
      "An integer field making each environment build distinct"))

  course = property(lambda self: self.assignment.course)


class SolutionFile(BaseModel):
  name = models.CharField(max_length=48, help_text=("The name of the Solution file."))
  code = models.TextField(blank=True, help_text=("The code in a file."))
  path = models.CharField(null=True, blank=True, max_length=500, help_text=(
      "Optional file path, delimited by slashes, to indicate a directory structure."))

  environment = models.ForeignKey(Environment, on_delete=models.CASCADE,
                                  related_name="solutionFiles", help_text=("The related environment_id."))

  course = property(lambda self: self.environment.course)


class HelperFile(BaseModel):
  name = models.CharField(max_length=48, help_text=("The name of the Helper file."))
  code = models.TextField(blank=True, help_text=("The code in a file."))
  path = models.CharField(null=True, blank=True, max_length=500, help_text=(
      "Optional file path, delimited by slashes, to indicate a directory structure."))
  environment = models.ForeignKey(Environment, on_delete=models.CASCADE,
                                  related_name="helperFiles", help_text=("The related environment_id."))

  course = property(lambda self: self.environment.course)


class SourceFile(BaseModel):
  code = models.TextField(blank=True, help_text=("The code."))
  name = models.CharField(max_length=48, help_text=("The name of the Test Group file."))
  environment = models.ForeignKey(Environment, on_delete=models.CASCADE,
                                  related_name="sourceFiles", help_text=("The related environment_id."))

  course = property(lambda self: self.environment.course)

###############################################################################


def getCurrentFiles(submission):
  files = submission.files.all()
  currentFileByPath = {}
  for f in files:
    path = (re.sub(r'/^\/+|\/+$', '', f.path) + '/' + f.name) if f.path else f.name
    if (path not in currentFileByPath) or (f.created >= currentFileByPath[path].created):
      currentFileByPath[path] = f

  currentFiles = []
  for path in currentFileByPath:
    currentFiles.append(currentFileByPath[path])
  return currentFiles


def getLatestSubmissionTests(submission):
  submission_tests = submission.tests.all()
  current_subtest_by_case = {}
  for st in submission_tests:
    if st.testCase.id not in current_subtest_by_case:
      current_subtest_by_case[st.testCase.id] = st
    else:
      if st.created > current_subtest_by_case[st.testCase.id].created:
        current_subtest_by_case[st.testCase.id] = st

  return current_subtest_by_case.values()


def calculate_grade(submission):
  # key = category id (0 = no rubricComment), value = aggregate deductions
  deductions = {}
  deductions[0] = 0
  currentFiles = getCurrentFiles(submission)
  for file in currentFiles:
    for comment in file.comments.all():
      if comment.rubricComment:
        if comment.rubricComment.category.id in deductions.keys():
          deductions[
              comment.rubricComment.category.id] += comment.rubricComment.pointDelta
        else:
          deductions[
              comment.rubricComment.category.id] = comment.rubricComment.pointDelta
      elif comment.pointDelta:
        deductions[0] += comment.pointDelta

  # Apply category caps
  for key in deductions:
    if key != 0:
      category = RubricCategory.objects.get(id=key)
      if category.pointLimit is not None:
        if category.pointLimit < 0:
          deductions[key] = max(deductions[key], category.pointLimit)
        else:
          deductions[key] = min(deductions[key], category.pointLimit)

  # Now account for points corresponding to tests
  tests = getLatestSubmissionTests(submission)
  counter = 0
  for test in tests:
    if test.passed:
      counter += test.testCase.pointsPass
    else:
      counter += test.testCase.pointsFail

  # Reduce to deduction
  if submission.assignment.additiveGrading:
    return -1 * sum(deductions.values()) + counter
  else:
    return submission.assignment.points - sum(deductions.values()) + counter


def updateSubmissionHistory(submission):
  oldStudents = [
      x.student for x in submission.histories.all().prefetch_related('student')]
  newStudents = submission.students.all()
  for student in newStudents:
    if (student not in oldStudents):
      SubmissionHistory.objects.create(
          submission=submission, student=student, hasViewed=False)
  for student in oldStudents:
    if (student not in newStudents):
      SubmissionHistory.objects.filter(
          student=student, submission=submission).delete()
  return


############# Signals #########################################################

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
  if created:
    profile = Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
  instance.profile.save()


############# TRIGGER GRADE COMPUTATION #######################################

# Don't need to handle delete cases, since deleting a rubric category => deletes
# rubric comments => modifies comment objects (by setting
# comment.rubricComment to null)


@receiver(post_save, sender=RubricCategory)
def update_submission_grade_after_rubricCategory_save(sender, instance, **kwargs):
  for rubricComment in instance.rubricComments.all():
    rubricComment.save()


@receiver(post_save, sender=RubricComment)
def update_submission_grade_after_rubricComment_save(sender, instance, **kwargs):
  for comment in instance.comments.all():
    comment.file.submission.save()

# We only want to update submission history if the students change


@receiver(m2m_changed, sender=Submission.students.through)
def update_histories_on_student_change(sender, instance, **kwargs):
  updateSubmissionHistory(instance)


@receiver(post_save, sender=Submission)
def update_assignment(sender, instance, **kwargs):
  instance.assignment.save()


@receiver(post_save, sender=File)
def save_submission_from_file(sender, instance, **kwargs):
  instance.submission.save()


@receiver(post_delete, sender=File)
def save_submission_from_file_delete(sender, instance, **kwargs):
  instance.submission.save()


@receiver(post_save, sender=Comment)
def save_submission_from_comment(sender, instance, **kwargs):
  instance.file.submission.save()


@receiver(post_delete, sender=Comment)
def save_submission_from_comment_delete(sender, instance, **kwargs):
  instance.file.submission.save()


@receiver(pre_save, sender=Submission)
def updateRegradeResponse(sender, instance, **kwargs):
  if(not instance.questionResponse):
    return
  try:
    obj = Submission.objects.get(pk=instance.pk)
  except sender.DoesNotExist:
    pass
  else:
    if not obj.questionResponse == instance.questionResponse:
      instance.responseDate = now()
