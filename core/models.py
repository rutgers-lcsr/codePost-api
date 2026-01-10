from __future__ import annotations

from ast import For
from asyncio.log import logger
from datetime import datetime, timedelta
from decimal import Decimal
import re
import hashlib
import uuid
import shutil

from django.contrib.auth.models import User  # type: ignore[assignment]
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Avg
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils.timezone import now
from django.db.models import ManyToManyField
from jsonfield import JSONField
from regex import F
from rest_framework.authtoken.models import Token
from zmq import has
from django.utils import timezone
from django.utils.text import slugify
from core.validators import validate_hex_color
from typing import Callable, Optional, TypeVar, Dict, Any, TYPE_CHECKING
from codepost.settings import DEBUG, MEDIA_ROOT
from django.db import models
import os

def get_default_token_expiry():
  """Returns datetime 5 minutes from now for OneTimeToken expiration."""
  if DEBUG:
    return timezone.now() + timedelta(days=1)

  return timezone.now() + timedelta(minutes=5)

if TYPE_CHECKING:
    from django.db.models import Manager as RelatedManager
    
    # Extend User model with custom reverse relationships for type checking
    # This tells Pylance about the relationships defined in our models
    class User(User):  # type: ignore[no-redef]
        profile: Profile
        student_submissions: RelatedManager[Submission]
        grader_submissions: RelatedManager[Submission]
        grader_regraded_submissions: RelatedManager[Submission]
        student_submissionHistories: RelatedManager[SubmissionHistory]
        student_courses: RelatedManager[Course]
        grader_courses: RelatedManager[Course]
        courseAdmin_courses: RelatedManager[Course]
        student_inactive_courses: RelatedManager[Course]
        grader_inactive_courses: RelatedManager[Course]
        courseAdmin_inactive_courses: RelatedManager[Course]
        leader_sections: RelatedManager[Section]
        student_sections: RelatedManager[Section]
    

# Notes
# Consider using indexes (db_index) to speed up common queries
# (https://stackoverflow.com/questions/14786413/add-indexes-db-index-true)

class BaseModel(models.Model):
  created: models.DateTimeField[datetime, datetime] = models.DateTimeField(editable=False, default=now)
  modified: models.DateTimeField[datetime, datetime] = models.DateTimeField(default=now)

  class Meta:
    abstract = True

  def save(self, *args: Any, **kwargs: Any) -> None:
    if self.pk:
      ''' Update '''

      ######################################################################
      # Check which fields have been updated
      ######################################################################
      cls = self.__class__
      old = cls.objects.get(pk=self.pk)
      new = self
      changed_fields: list[str] = []
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
  if TYPE_CHECKING:
    id: int
    profiles: RelatedManager[Profile]
    courses: RelatedManager[Course]
    
  name = models.CharField(max_length=64, unique=True,
                          help_text=("The name of the organization."))
  shortname = models.CharField(max_length=12, unique=True, help_text=(
      "A shortname for the organization (e.g. Princeton University -> PU)"))
  email_domain = models.CharField(max_length=64, blank=True, null=True, help_text=(
      "The email domain associated with the organization."))

  sso_enabled = models.BooleanField(default=False, help_text=("If True, new users in this organization are automatically activated and assume external authentication."))
  sso_provider = models.CharField(max_length=32, blank=True, null=True, help_text=("The SSO provider (e.g. CAS, AZURE, OIDC, GOOGLE)."))
  sso_config = JSONField(default=dict, blank=True, help_text=("JSON configuration for the SSO provider."))
  send_welcome_email = models.BooleanField(default=True, help_text=("If False, suppresses welcome/added-to-course emails for users in this organization."))

  class Meta:
    ordering = ('name',)

  def __str__(self):
    return self.shortname


# Internal Model - not published in public API
# https://wsvincent.com/django-custom-user-model-tutorial/


class Profile(BaseModel):
  if TYPE_CHECKING:
    id: int
    
  user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile", help_text=(
      "The username of the related user."))
  api_token = models.ForeignKey(
      Token, on_delete=models.SET_NULL, blank=True, null=True)
  organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True,
                                   null=True, related_name="profiles", help_text=("The related organization_id"))
  canCreateCourses = models.BooleanField(default=False)
  canModifyRosters = models.BooleanField(default=False)
  isOrgStaff = models.BooleanField(default=False, help_text=("If True, user can manage Organization settings (SSO, Defaults)."))
  pendingValidation = models.BooleanField(default=False)
  showProductTips = models.BooleanField(default=True)
  isPasswordSet = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, the user has set a password for their account. If False, the user has not set a password and should be prompted to do so."))

  stripeCustomerId = models.CharField(max_length=96, unique=True, null=True, blank=True, help_text=(
      "The customer_id from the Stripe customer object."))

  def __init__(self, *args, **kwargs):
    # Remove deprecated stripeCustomerId if provided
    if 'stripeCustomerId' in kwargs:
      kwargs.pop('stripeCustomerId')
    super().__init__(*args, **kwargs)

  def __str__(self):
    return self.user.email

class OneTimeToken(BaseModel):
  if TYPE_CHECKING:
    id: int
    user: models.ForeignKey[User, User]

  user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="one_time_tokens", help_text=(
      "The username of the related user."))
  token = models.CharField(max_length=255, unique=True, help_text=(
      "The one-time token string."), default=uuid.uuid4)
  expires_at = models.DateTimeField(default=get_default_token_expiry)

  used = models.BooleanField(default=False, help_text=("Whether the token has been used."))

  def is_valid(self):
    return not self.used and timezone.now() < self.expires_at

  

  def __str__(self):
    return f"OneTimeToken for {self.user.email} expiring at {self.expires_at}"

class Course(BaseModel):
  if TYPE_CHECKING:
    id: int
    sections: RelatedManager[Section]
    assignments: RelatedManager[Assignment]
    files: RelatedManager[CourseFile]

  name = models.CharField(max_length=36, help_text=("The name of the course."))
  organization = models.ForeignKey(Organization, on_delete=models.CASCADE,
                                   related_name="courses", help_text=("The related organization_id"))
  period = models.CharField(max_length=32, help_text=(
      "A string describing the period (e.g. F2019, T32019, etc."))
  archived = models.BooleanField(default=False, help_text=("If True, the course will not be editable."))

  # ManyToMany relationships - accessed via Manager (e.g., course.students.all())
  students = models.ManyToManyField(User, related_name="student_courses", help_text=(
      "A list of usernames of students enrolled in the course."))
  inactive_students = models.ManyToManyField(
      User,
      related_name="student_inactive_courses",
      help_text=("A list of usernames of students unenrolled in the course."),
      blank=True,
  )
  inactive_graders = models.ManyToManyField(
    User,
    related_name="grader_inactive_courses",
    help_text=(
      "A list of usernames of graders inactive in the course."),
    blank=True,
    )
  inactive_courseAdmins = models.ManyToManyField(
    User, 
    related_name="courseAdmin_inactive_courses", 
    help_text=(
      "A list of usernames of admins inactive in the course."),
    blank=True,
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

  def validate_manual_payments(self):
    if not isinstance(self, list):
        raise ValidationError('Must be an array')

    for item in self:
        if not set(['id', 'timestamp', 'amount', 'description', 'email']).issubset(item.keys()):
            raise ValidationError('Each manual payment must have an id, timestamp, amount, description, and email field')
        
  manual_payments = JSONField(default=list, help_text="An array of manual payments", validators=[validate_manual_payments], blank=True)
  waiver_requested = models.BooleanField(default=False, help_text=("If True, the course has requested a waiver."))
  studentsCanSeeGraders = models.BooleanField(default=False, help_text=(
      "If True, students can see the grader who graded their submission."))
  
  expiration_date = models.DateTimeField(null=True, blank=True, help_text=("The date when the course will be automatically deleted."))

  # AI Configuration for comment generation
  AI_PROVIDER_CHOICES = [
      ('gemini', 'Google Gemini'),
      ('openai', 'OpenAI'),
      ('ollama', 'Ollama (Self-hosted)'),
      ('custom', 'Custom Provider'),
  ]
  ai_provider = models.CharField(
      max_length=32,
      blank=True,
      null=True,
      choices=AI_PROVIDER_CHOICES,
      help_text="AI provider for comment generation"
  )
  ai_api_key = models.TextField(
      blank=True,
      null=True,
      help_text="API key for AI provider (stored encrypted)"
  )
  ai_base_url = models.URLField(
      blank=True,
      null=True,
      help_text="Base URL for Ollama or custom provider"
  )
  ai_model = models.CharField(
      max_length=64,
      blank=True,
      null=True,
      help_text="Model name (e.g., gemini-1.5-flash, gpt-4)"
  )

  class Meta:
    unique_together = ('name', 'period', 'organization')
    ordering = ('name', 'period')

  def __str__(self):

    return str(self.name) + " | " + self.period


##########################################################################

############# Course Infrastructure Section ##############################


class Section(BaseModel):
  if TYPE_CHECKING:
    id: int
    course: models.ForeignKey[Course, Course]
    
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
  if TYPE_CHECKING:
    id: int
    environment: Environment
    submissions: RelatedManager[Submission]
    files: RelatedManager[AssignmentFile]
    rubricCategories: RelatedManager[RubricCategory]
    testCategories: RelatedManager[TestCategory]
    dataSets: RelatedManager[AssignmentDataSet]
    course: models.ForeignKey[Course, Course]
    uploadDueDate: models.DateTimeField[datetime, datetime]
    maxLateDays: models.IntegerField[int, int]

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
  points = models.DecimalField(validators=[MinValueValidator(0)], max_digits=5,
                               decimal_places=2, help_text=("Total points for the assignment."))
  mean = models.DecimalField(validators=[MinValueValidator(0)], max_digits=5, decimal_places=2, blank=True, null=True, help_text=(
      "The average grade of the assignment. Null if no submissions yet"))
  median = models.DecimalField(validators=[MinValueValidator(0)], max_digits=5, decimal_places=2, blank=True, null=True, help_text=(
      "The median grade of the assignment. Null if no submissions yet"))
  sortKey = models.IntegerField(default=0, help_text=(
      "Optional integer to specify the order of a Course's Assignments."))

  # Settings
  hideGrades = models.BooleanField(default=False, help_text=(
      "A boolean field. 'True' if the students should not see their grades for this assignment. 'False' otherwise."))

  feedbackReleased = models.BooleanField(default=False, help_text=(
      "A boolean field. 'True' if grades/feedback are released for students to view. 'False' otherwise."))

  anonymousGrading = models.BooleanField(default=False, help_text=(
      "A boolean field. If 'True', graders will not have access to the students field of submission objects, unless they have elevated privileges."))
  commentFeedback = models.BooleanField(default=True, help_text=(
      "A boolean field. If True, students can provide feedback on rubric comments."))
  allowStudentUpload = models.BooleanField(default=False, help_text=(
      "A boolean field. If true, students will be allowed to upload submissions until the upload due date."))
  allowStudentUploadWithPartners = models.BooleanField(default=False, help_text=("A boolean field. If true, students will be allowed to invite partners to their submission."))
  uploadDueDate = models.DateTimeField(null=True, help_text=(
      "The date after which students are not allowed to upload submissions. Only useful if allowStudentUpload is set to True."))
  maxLateDays = models.IntegerField(default=2, help_text=(
      "An integer representing the maximum number of late days to continue to accept submissions for this assignment."))
  
  liveFeedbackMode = models.BooleanField(default=False, help_text=(
      "A boolean field. If true, students can see their submission and comments before finalization and published"))
  additiveGrading = models.BooleanField(default=False, help_text=(
      "A boolean field. If true, grades begin at 0 (instead of assignment.points)"))
  hideGradersFromStudents = models.BooleanField(default=True, help_text=(
      "A boolean field. If True, the graders of a submission will be hidden from students."))
  studentsCanSeeGraders = models.BooleanField(null=True, blank=True, default=None, help_text=(
      "If set, overrides course setting. If True, students can see graders for this assignment."))
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

  # AI-powered comment generation
  ai_system_prompt = models.TextField(
      blank=True,
      default="",
      help_text="System prompt for AI comment generation. "
                "Placeholders: {assignment_name}, {file_content}, {selected_content}, {rubric_context}, {grader_draft}"
  )


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
  if TYPE_CHECKING:
    id: int
    assignment: Assignment
    assignment_id: int | None
    rubricComments: RelatedManager[RubricComment]

  assignment: Assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,  # type: ignore[assignment]
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
  if TYPE_CHECKING:
    id: int
    category: RubricCategory
    category_id: int | None
    comments: RelatedManager[Comment]

  text = models.TextField(blank=True, help_text=("The text on the rubric comment."))
  explanation = models.TextField(blank=True, help_text=("The explanation of a rubric comment shown to students."))
  instructionText = models.TextField(blank=True, help_text=(
      "Text shown to the grader in the custom text field of an instance comment."))
  templateTextOn = models.BooleanField(default=False, help_text=(
      "If True, instruction text will pre-populate instance comments."))
  pointDelta = models.DecimalField(max_digits=5, decimal_places=2, help_text=(
      "The points deducted. A negative number represents a bonus."))
  category: RubricCategory = models.ForeignKey(RubricCategory, on_delete=models.CASCADE,  # type: ignore[assignment]
                               related_name="rubricComments", help_text=("The related rubricCategory_id"))
  sortKey = models.IntegerField(default=0, help_text=(
      "Optional integer to specify the order of a Rubric Category's comments."))
  name = models.CharField(max_length=255, null=True, blank=True)


  course = property(lambda self: self.category.course)


###############################################################################


############# Submissions Section #############################################

class Submission(BaseModel):
  if TYPE_CHECKING:
    id: int
    assignment: Assignment
    grader: User | None
    questionResponder: User | None
    files: RelatedManager[SubmissionFile]
    histories: RelatedManager[SubmissionHistory]
    tests: RelatedManager[SubmissionTest]

  assignment: Assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,  # type: ignore[assignment]
                                 related_name="submissions", help_text=("The related assignment_id."))
  students = models.ManyToManyField(User, related_name="student_submissions", help_text=(
      "A list of usernames of students for the submission."))
  grader: User | None = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL, related_name="grader_submissions", help_text=(  # type: ignore[assignment]
      "The username of the assigned grader for the submission."))
  isFinalized = models.BooleanField(default=False, help_text=(
      "A boolean field. 'True' if the submission is finalized. 'False' otherwise."))
  dateEdited = models.DateTimeField(default=now, help_text=(
      "The date this submission (or any of its associated files or comments) was last edited."))
  grade = models.DecimalField(validators=[MinValueValidator(0)], max_digits=5, decimal_places=2,
                              blank=True, null=True, help_text=("The grade for the submission. Null if not graded yet."))
  queueOrderKey = models.IntegerField(default=0, help_text=(
      "Index used to order the queue from which graders draw submissions. Will sort low to high."))
  gradeFrozen = models.BooleanField(default=False, help_text=(
      "A boolean field. If 'True', the submissions grade will not be re-calculated based on the current comments applied to it. Warning: this can cause grade to become out of sync with the submission's comments."))
  dateUploaded = models.DateTimeField(
      default=None, help_text=("The date this submission was created. None if just created, and files haven't been uploaded yet. Used for Celery tasks."), null=True)

  lateDayCreditsUsed = models.IntegerField(default=0, help_text=(
      "The number of Late Day Credits used by the Submission."))

  # Student question
  questionIsOpen = models.BooleanField(default=False, help_text=(
      "A boolean field. If true the submission has an open question."))
  questionIsRegrade = models.BooleanField(default=False, help_text=(
      "A boolean field. If 'True', the submission's question is a regrade request."))
  questionResponder: User | None = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL,  # type: ignore[assignment]
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
  """Deprecated model - kept for backwards compatibility only."""
  pass


class File(BaseModel):
  if TYPE_CHECKING:
    id: int
  
  name = models.CharField(max_length=250, help_text=("The name of the file."))
  data = models.TextField(help_text=("The data in a file. should be utf-8 encoded text."), default="", null=False)
  extension = models.CharField(max_length=36, help_text=(
      "The extension for the file (e.g. '.java' or '.py'"))
  path = models.CharField(null=True, blank=True, max_length=500, help_text=(
      "Optional file path, delimited by slashes, to indicate a directory structure."))

  course = property(lambda self: self.get_course())
  hash = models.CharField(max_length=256, help_text=("The SHA-256 hash of the file."), default="")
  
  def __repr__(self):
    return super().__repr__() + f" (name={self.name}, extension={self.extension})"
  
  
  def get_course(self):
    try:
      return self.submissionfile.submission.assignment.course  # type: ignore[attr-defined]
    except (AttributeError, ObjectDoesNotExist):
      pass
    try:
      return self.assignmentfile.assignment.course  # type: ignore[attr-defined]
    except (AttributeError, ObjectDoesNotExist):
      pass
    try:
      return self.coursefile.course  # type: ignore[attr-defined]
    except (AttributeError, ObjectDoesNotExist):
      pass
    return None
  def get_file_info(self) -> tuple[Optional[Submission], Optional[Assignment], Optional[Course]]:
    """ Returns the associated Submission, Assignment, and Course for this File, if any."""
    submission = None
    assignment = None
    course = None
    
    try:
      if hasattr(self, 'submissionfile'):
        submission = self.submissionfile.submission  # type: ignore[attr-defined]
        assignment = submission.assignment
        course = assignment.course
      elif hasattr(self, 'assignmentfile'):
        assignment = self.assignmentfile.assignment  # type: ignore[attr-defined]
        course = assignment.course
      elif hasattr(self, 'coursefile'):
        course = self.coursefile.course  # type: ignore[attr-defined]
    except (AttributeError, ObjectDoesNotExist):
      # Related objects may have been deleted during cascade deletion
      pass

    return submission, assignment, course

  @staticmethod
  def get_file_obj(file_id: int) -> tuple[File|SubmissionFile|AssignmentFile|CourseFile, Optional[Submission], Optional[Assignment], Optional[Course]]:
    file = File.objects.get(id=file_id)
    if not file:
      raise ValueError(f"File with id {file_id} not found")
    submission = None
    assignment = None
    course = None
    try:
      if hasattr(file, 'submissionfile'):
        submission = file.submissionfile.submission # type: ignore[attr-defined]
        assignment = submission.assignment
        course = assignment.course
      elif hasattr(file, 'assignmentfile'):
        assignment = file.assignmentfile.assignment  # type: ignore[attr-defined]
        course = assignment.course
      elif hasattr(file, 'coursefile'):
        course = file.coursefile.course  # type: ignore[attr-defined]
    except (AttributeError, ObjectDoesNotExist):
      # Related objects may have been deleted during cascade deletion
      pass

    return file, submission, assignment, course
  
  @property
  def handler(self):
      """
      Returns the appropriate FileHandler for this file.
      Cached on the instance to avoid re-creation.
      """
      if not hasattr(self, '_handler'):
          from core.services.file_handlers.factory import FileHandlerFactory
          self._handler = FileHandlerFactory.get_handler(self)
      return self._handler

  def __getattr__(self, name):
      # Delegate unknown attributes to the handler
      # Avoid recursion if handler is missing
      if name in ['_handler', 'handler']:
          raise AttributeError(name)
          
      try:
          return getattr(self.handler, name)
      except AttributeError:
          raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

  def save(self, *args, **kwargs):
    # Check if trying to use deprecated 'code' field
    if hasattr(self, 'code') and self.code:  # type: ignore[attr-defined]
      raise Exception("File.code is deprecated. Use File.data instead.")
 
    # Normalize newlines
    if '\\r\\n' in self.data:
      self.data = self.data.replace("\\r\\n", "\\n")
    
    # Ensure utf-8 encoding
    self.data = self.data.encode('utf-8').decode('utf-8')
    self.hash = hashlib.sha256(self.data.encode('utf-8')).hexdigest()
    
    # Infer extension from name if not provided
    if not self.extension:
      match = re.search(r'(\.[^.]+)$', self.name)
      if match:
        self.extension = match.group(1)
      else:
        # Try to use handler logic? No, handler needs extension usually.
        # But we could potentially use content sniffing in handler.
        # For now keeping existing logic but maybe allowing handler to refine?
        raise ValidationError("File extension could not be inferred from file name. Please provide an extension.")
      
    
    return super(File, self).save(*args, **kwargs)
  



class SubmissionFile(File):
  if TYPE_CHECKING:
    id: int
    submission: Submission
    comments: RelatedManager[Comment]

  submission: Submission = models.ForeignKey(Submission, on_delete=models.CASCADE,  # type: ignore[assignment]
                                  related_name="files", help_text=("The related submission_id."))
  hiddenBeforePublish = models.BooleanField(default=False, help_text=(
      "Whether this file should hidden to students before their feedback has been published. This is for autogenerated test files that shouldn't be exposed to students on upload."))


def dataset_upload_path(instance: AssignmentDataSet|Assignment, filename: str) -> str:
  """
  Generate hierarchical upload path for dataset files.
  Path format: assignment_datasets/<org_shortname>/<course_name>/<period>/<assignment_name>/<filename>
  """
  if isinstance(instance, AssignmentDataSet):
    assignment = instance.assignment
  else:
    assignment = instance
  course = assignment.course
  org = course.organization
  # Sanitize path components for filesystem safety
  org_safe = slugify(org.shortname)
  course_safe = slugify(course.name)
  period_safe = slugify(course.period)
  assignment_safe = slugify(assignment.name)
  filename_safe = os.path.basename(filename)
  
  return f'{org_safe}/{course_safe}/{period_safe}/{assignment_safe}/{filename_safe}'


class AssignmentDataSet(BaseModel):
  if TYPE_CHECKING:
    id: int
    assignment: models.ForeignKey[Assignment, Assignment]

  assignment = models.ForeignKey("Assignment", on_delete=models.CASCADE, related_name="dataSets", help_text=("The related assignment_id."))  
  name = models.CharField(max_length=64, help_text=("The name of the data set."))
  description = models.TextField(blank=True, help_text=("Optional description of the data set."))
  file = models.FileField(upload_to=dataset_upload_path, help_text=("The data set file"))
  
  # Path where the dataset should be mounted in the execution environment
  # Defaults to ~/shared/<dataset_name> to match existing student environment
  mount_path = models.CharField(
    max_length=256, 
    blank=True,
    help_text=("Path where dataset will be mounted in execution environment. Can be an absolute path (e.g. '/etc/config.json') or a relative path (e.g. 'mnist'). Relative paths are mounted under '/shared'."))
  
  # Whether this dataset is available to students during upload/execution
  is_active = models.BooleanField(
    default=True,
    help_text=("If True, this dataset will be mounted during code execution."))

  course = property(lambda self: self.assignment.course)
  
  def save(self, *args, **kwargs):
    # Set default mount_path if not provided
    if not self.mount_path and self.name:
      # Sanitize name for filesystem use - keep dots for file extensions
      safe_name = self.name.lower().replace(' ', '_')
      safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-.')
      self.mount_path = f'shared/{safe_name}'
    
    super(AssignmentDataSet, self).save(*args, **kwargs)
  
  class Meta:
    unique_together = ('assignment', 'name')
    ordering = ('name',)

class CachedExecutionResult(BaseModel):
  """
  Stores cached execution results for files (notebooks/Python scripts).
  Allows students to see grader's execution output without re-running.
  """
  if TYPE_CHECKING:
    id: int
    file: models.ForeignKey[File, File]
    executed_by: models.ForeignKey[User, User]
  
  # Generic foreign key to support any File subclass
  file = models.ForeignKey(
    "File",
    on_delete=models.CASCADE,
    related_name="cached_executions",
    help_text="The file this execution result is for"
  )
  
  # Execution metadata
  executed_by = models.ForeignKey(
    User,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    help_text="User who executed the code"
  )
  executed_at = models.DateTimeField(
    auto_now_add=True,
    help_text="When the code was executed"
  )
  
  # File content tracking to detect changes
  file_content_hash = models.CharField(
    max_length=64,
    help_text="SHA256 hash of file content at execution time"
  )
  
  # Execution results (stored as JSON)
  output_data = models.JSONField(
    help_text="Execution output data with cells"
  )
  
  # Execution context
  execution_time_seconds = models.FloatField(
    null=True,
    blank=True,
    help_text="Time taken to execute in seconds"
  )
  
  class Meta:
    ordering = ('-executed_at',)
    indexes = [
      models.Index(fields=['file', '-executed_at']),
      models.Index(fields=['file_content_hash']),
    ]
  
  def __str__(self):
    return f"Execution of {self.file.name} at {self.executed_at}"
  
  @classmethod
  def get_cached_result(cls, file):
    """
    Get cached execution result for a file if valid.
    
    Args:
      file: File instance to get cached result for
    
    Returns:
      CachedExecutionResult if valid cache exists, None otherwise
    """
    import hashlib
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"[CachedExecutionResult.get] Checking cache for file {file.id}")
    
    # Get file content - File subclasses use 'data', some special files use 'code'
    file_content = getattr(file, 'data', None) or getattr(file, 'code', '')
    if not file_content:
      logger.warning(f"[CachedExecutionResult.get] File {file.id} has no content")
      return None
    
    # Calculate current file content hash
    current_hash = hashlib.sha256(file_content.encode('utf-8')).hexdigest()
    logger.info(f"[CachedExecutionResult.get] File {file.id} current hash: {current_hash[:16]}...")
    
    # Get most recent cached result for this file
    try:
      cached = cls.objects.filter(
        file=file,
        file_content_hash=current_hash
      ).latest('executed_at')
      logger.info(f"[CachedExecutionResult.get] Cache HIT for file {file.id}, cache ID: {cached.id}")
      return cached
    except cls.DoesNotExist:
      logger.info(f"[CachedExecutionResult.get] Cache MISS for file {file.id}")
      return None
  
  def get_cached_formated_response(self,file:File):
    # Return in the same format as fresh execution
    response_data = {
        "success": True,
        "output_data": self.output_data,
        "file_id": file.id,
        "file_name": file.name,
        "error": None,
        "execution_time": self.execution_time_seconds,
        "cached": True,
        "executed_at": self.executed_at.isoformat(),
        "executed_by": self.executed_by.username if self.executed_by else None,
    }
    submission, assignment, course = file.get_file_info()
    if submission:
      response_data["submission_id"] = submission.id
    if assignment:
      response_data["assignment_id"] = assignment.id
    if course:
      response_data["course_id"] = course.id


    return response_data

  @classmethod
  def save_execution_result(cls, file, output_data, executed_by=None, execution_time=None):
    """
    Save execution result to cache.
    
    Args:
      file: File instance
      output_data: Execution output data (dict with cells)
      executed_by: User who executed the code
      execution_time: Time taken to execute in seconds
    
    Returns:
      Created CachedExecutionResult instance
    """
    import hashlib
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"[CachedExecutionResult.save] Attempting to save cache for file {file.id}")
    
    # Get file content - File subclasses use 'data', some special files use 'code'
    file_content = getattr(file, 'data', None) or getattr(file, 'code', '')
    if not file_content:
      logger.warning(f"[CachedExecutionResult.save] File {file.id} has no content, skipping cache")
      return None
    
    # Calculate file content hash
    content_hash = hashlib.sha256(file_content.encode('utf-8')).hexdigest()
    logger.info(f"[CachedExecutionResult.save] File {file.id} content hash: {content_hash[:16]}...")
    
    # Delete old cache entries for this file with the same content hash
    # This ensures we always have the latest execution result
    try:
      old_count = cls.objects.filter(file=file, file_content_hash=content_hash).count()
      if old_count > 0:
        logger.info(f"[CachedExecutionResult.save] Deleting {old_count} old cache entries for file {file.id}")
        cls.objects.filter(file=file, file_content_hash=content_hash).delete()
    except Exception as e:
      logger.warning(f"[CachedExecutionResult.save] Failed to delete old cache entries: {e}")
    
    # Create cached result
    try:
      cached = cls.objects.create(
        file=file,
        executed_by=executed_by,
        file_content_hash=content_hash,
        output_data=output_data,
        execution_time_seconds=execution_time
      )
      logger.info(f"[CachedExecutionResult.save] Successfully saved cache for file {file.id}, cache ID: {cached.id}")
      return cached
    except Exception as e:
      logger.error(f"[CachedExecutionResult.save] Failed to create cache record: {e}", exc_info=True)
      return None


class AssignmentFile(File):
  if TYPE_CHECKING:
    id: int
    assignment: Assignment
    
  assignment: Assignment = models.ForeignKey("Assignment", on_delete=models.CASCADE,  # type: ignore[assignment]
                                 related_name="files", help_text=("The related assignment_id."))
  required = models.BooleanField(
      default=False, help_text="If student upload is enabled, a file with this name and extension will be required.")
  description = models.TextField(blank=True, help_text=("Optional description shown to students."))
  isVisible = property(lambda self: self.assignment.isVisible)

  course = property(lambda self: self.assignment.course)


class CourseFile(File):
  if TYPE_CHECKING:
    id: int
    course: Course
    
  course: Course = models.ForeignKey(Course, on_delete=models.CASCADE,  # type: ignore[assignment]
                             related_name="files", help_text=("The related course_id."))

  def get_course(self):
    return self.course

class CommentTag(BaseModel):
  if TYPE_CHECKING:
    id: int
    tag_comments: RelatedManager[Comment]
    
  label = models.CharField(max_length=64, unique=True, help_text=("The tag label."))

  # FIXME: Only for internal checking, should also create serializer field
  def save(self, *args, **kwargs):
    self.label = self.label.lower().strip()

    super(CommentTag, self).save(*args, **kwargs)



class Comment(BaseModel):
  if TYPE_CHECKING:
    id: int
    rubricComment: RubricComment | None
    author: User
    file: SubmissionFile
    
  text = models.TextField(blank=True, help_text=("The text on the comment"))
  pointDelta = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, help_text=(
      "The points deducted. A negative number represents a bonus."))
  rubricComment: RubricComment | None = models.ForeignKey(RubricComment, null=True, blank=True, on_delete=models.SET_NULL,  # type: ignore[assignment]
                                    related_name="comments", help_text=("The related rubricComment_id. Null if no rubric comment linked."))
  author: User = models.ForeignKey(User, on_delete=models.CASCADE, help_text=(  # type: ignore[assignment]
      "The username of the author of the comment."))
  file: SubmissionFile = models.ForeignKey(SubmissionFile, on_delete=models.CASCADE,  # type: ignore[assignment]
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
  if TYPE_CHECKING:
    id: int
    assignment: Assignment
    testCases: RelatedManager[TestCase]

  assignment: Assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,  # type: ignore[assignment]
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
  if TYPE_CHECKING:
    id: int
    testCategory: TestCategory
    instances: RelatedManager[SubmissionTest]

  testCategory: TestCategory = models.ForeignKey(TestCategory, on_delete=models.CASCADE,  # type: ignore[assignment]
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
  expectPlot = models.BooleanField(default=False, help_text=("If True, the test will only pass if a plot is generated."))
  dataSet = models.ForeignKey("AssignmentDataSet", null=True, blank=True, on_delete=models.SET_NULL, help_text=("The dataset to mount for this test."))
  targetCellId = models.CharField(max_length=64, blank=True, null=True, help_text=("The ID of the notebook cell to target for execution."))

  course = property(lambda self: self.testCategory.course)


class SubmissionTest(BaseModel):
  if TYPE_CHECKING:
    id: int
    submission: Submission
    testCase: TestCase
    
  submission: Submission = models.ForeignKey(Submission, on_delete=models.CASCADE,  # type: ignore[assignment]
                                 related_name="tests", help_text=("The related submission_id."))
  testCase: TestCase = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name="instances",  # type: ignore[assignment]
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
  if TYPE_CHECKING:
    id: int
    submission: Submission
    student: User
    
  submission: Submission = models.ForeignKey(Submission, on_delete=models.CASCADE,  # type: ignore[assignment]
                                 related_name="histories", help_text=("The related submission_id."))
  student: User = models.ForeignKey(User, on_delete=models.CASCADE, related_name="student_submissionHistories", help_text=(  # type: ignore[assignment]
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
  if TYPE_CHECKING:
    id: int
    assignment: Assignment
  assignment: Assignment = models.OneToOneField(Assignment, on_delete=models.CASCADE,  # type: ignore[assignment]
                                    related_name="environment", help_text=("The related assignment__id."))
  dockerRunInstructions = JSONField(default=[], blank=True, help_text="Instructions to be added to the docker file with a RUN command.")
  language = models.CharField(max_length=25, choices=(
      ('python-3.12', 'python-3.12'),
      ('python-3.11', 'python-3.11'),
      ('python-3.10', 'python-3.10'),
      ('python-3.7', 'python-3.7'),
      ('python-2.7', 'python-2.7'),
      ('java', 'java'),
      ('java-17', 'java-17'),
      ('java-11', 'java-11'),
      ('c/c++', 'c/c++'),
      ('node-20', 'node-20'),
      ('node-18', 'node-18'),
      ('r-4', 'r-4'),
      ('ruby', 'ruby'),
      ('php', 'php')), default='python-3.7')
  buildType = models.CharField(max_length=25, choices=(
      ('default', 'default'),
      ('alpine', 'alpine'),
      ('ubuntu', 'ubuntu'),
      ('windows', 'windows')), default='default')
  dockerfile = models.TextField(default='', blank=True, help_text=(
      "A custom set of docker commands to append to the base image docker file"))
  compileText = models.TextField(default='', blank=True, help_text=(
      "Command to be run on every submission before tests"))
  allowNetworkAccess = models.BooleanField(default=False, help_text=(
      "A boolean field indicating whether tests should be run in a container that allows network access."))
  maxStudentTestRuns = models.PositiveIntegerField(null=True, blank=True, help_text=(
      "An integer field indicating the max times that tests will be run if tests are exposed."))
  maxExposedFailedTests = models.PositiveIntegerField(null=True, blank=True, help_text=(
      "An integer field indicating the limit of the number of failed tests that will be exposed to a student (nudge mode)."))

  buildID = models.PositiveIntegerField(default=0, help_text=(
      "An integer field making each environment build distinct"))
  
  # New fields for custom environment support
  image_name = models.CharField(max_length=255, null=True, blank=True, help_text="The Docker image name for this environment.")
  build_status = models.IntegerField(choices=((0, 'Not Built'), (1, 'Building'), (2, 'Success'), (3, 'Failed')), default=0)
  build_logs = models.TextField(default="", blank=True, help_text="Logs from the image build process.")
  last_built = models.DateTimeField(null=True, blank=True, help_text="Timestamp of the last build.")
  requirements = models.TextField(default="", blank=True, help_text="Python requirements.txt content.")
  env_vars = JSONField(default=dict, blank=True, help_text="Dictionary of environment variables to set in the Docker container.")
  auto_detect = models.BooleanField(default=True, help_text="Automatically detect environment settings from submissions.")
  
  # Convergence tracking
  convergence_stats = JSONField(default=dict, blank=True, help_text="Tracks module error counts: {module_name: occurrence_count}")
  successful_runs = models.PositiveIntegerField(default=0, help_text="Count of successful submission runs (for stability check)")
  total_runs = models.PositiveIntegerField(default=0, help_text="Total submission runs")
  
  # Image versioning and rollback
  current_build_version = models.PositiveIntegerField(default=1, help_text="Current image version number")
  image_history = JSONField(default=list, blank=True, help_text="List of {version, image_name, requirements, built_at, status}")
  convergence_pending = models.BooleanField(default=False, help_text="True if waiting to validate convergence after auto-update")
  convergence_failed_notified = models.BooleanField(default=False, help_text="True if admin was notified of convergence failure")

  course = property(lambda self: self.assignment.course)




#### Data

# AssignmentDataSet

@receiver(models.signals.pre_delete, sender=Assignment)
def delete_assignment(sender, instance: Assignment, **kwargs):
  # Delete any data releate to the assignment within the system. 
  # The database will handle deleting on cascade, but the docker images and datasets will need to be deleted manually.

  if instance.dataSets.all() and instance.dataSets.all().count() > 0:
    # just delete the directory assignment/dataset
    try:
      data_path = os.path.join(MEDIA_ROOT, dataset_upload_path(instance, filename=""))
      logger.info(f"Deleting dataset directory: {data_path}")
      shutil.rmtree(data_path)
    except Exception as e:
      logger.error(f"Failed to delete dataset directory: {e}")

###############################################################################


def getCurrentFiles(submission: Submission):
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


def calculate_grade(submission: Submission) -> Decimal:
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
    return Decimal(-1 * sum(deductions.values()) + counter)
  else:
    return Decimal(submission.assignment.points - sum(deductions.values()) + counter)


def updateSubmissionHistory(submission: Submission):
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
    Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
  # Ensure profile exists before trying to save
  try:
    instance.profile.save()
  except Profile.DoesNotExist:
    Profile.objects.create(user=instance)


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
  try:
    instance.submission.save()
  except AttributeError:
    # File doesn't have a submission (might be an AssignmentFile or CourseFile)
    pass


@receiver(post_delete, sender=File)
def save_submission_from_file_delete(sender, instance, **kwargs):
  try:
    # Check if this is a SubmissionFile (has a submission attribute)
    if hasattr(instance, 'submission') and instance.submission:
      instance.submission.save()
  except (Submission.DoesNotExist, AttributeError):
    # Submission was already deleted or doesn't exist
    pass


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


# Export all model classes for wildcard imports
__all__ = [
    "BaseModel",
    "Organization",
    "Profile",
    "Course",
    "Section",
    "Assignment",
    "RubricCategory",
    "RubricComment",
    "Submission",
    "File",
    "SubmissionFile",
    "AssignmentFile",
    "CourseFile",
    "CommentTag",
    "Comment",
    "TestCategory",
    "TestCase",
    "SubmissionTest",
    "SubmissionHistory",
    "AssignmentDataSet",
    "CachedExecutionResult",
]
