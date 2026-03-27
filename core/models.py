# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from __future__ import annotations

from ast import For
from asyncio.log import logger
from datetime import datetime, timedelta
from decimal import Decimal
import re
import hashlib
import uuid
import shutil
from encrypted_model_fields.fields import EncryptedCharField

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

  # AI Configuration at organization level
  AI_PROVIDER_CHOICES = [
      ('gemini', 'Google Gemini'),
      ('openai', 'OpenAI'),
      ('ollama', 'Ollama (Self-hosted)'),
      ('portkey', 'Portkey (Self-hosted)'),
      ('custom', 'Custom Provider'),
  ]
  AI_COURSE_POLICY_CHOICES = [
      ('all', 'All courses'),
      ('selected', 'Selected courses only'),
      ('none', 'Disabled'),
  ]
  ai_provider = models.CharField(
      max_length=32, blank=True, null=True, choices=AI_PROVIDER_CHOICES,
      help_text="AI provider for the organization"
  )
  ai_api_key = EncryptedCharField(
      max_length=512, blank=True, null=True,
      help_text="API key for AI provider (stored encrypted)"
  )
  ai_base_url = models.URLField(
      blank=True, null=True,
      help_text="Base URL for Ollama or custom provider"
  )
  ai_model = models.CharField(
      max_length=64, blank=True, null=True,
      help_text="Default model name (e.g., gemini-1.5-flash, gpt-4)"
  )
  ai_disabled = models.BooleanField(
      default=False,
      help_text="If True, all AI features are disabled for this organization"
  )
  ai_comments_disabled = models.BooleanField(
      default=False,
      help_text="If True, AI comment generation is disabled at the organization level"
  )
  ai_chat_disabled = models.BooleanField(
      default=False,
      help_text="If True, AI chat assistant is disabled at the organization level"
  )
  ai_course_policy = models.CharField(
      max_length=16, default='none', choices=AI_COURSE_POLICY_CHOICES,
      help_text="Controls which courses can use the organization's AI configuration: 'all', 'selected', or 'none'"
  )
  ai_enabled_courses = models.ManyToManyField(
      'Course', blank=True, related_name='ai_enabled_by_organizations',
      help_text="Courses explicitly enabled for the organization's AI configuration (used when ai_course_policy is 'selected')"
  )
  ai_token_rates = JSONField(
      default=dict, blank=True,
      help_text='Custom per-model token rates. JSON object mapping model names to {"input": <$/1M tokens>, "output": <$/1M tokens>}'
  )

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
  rubricEditors = models.ManyToManyField(User, related_name="rubricEditor_courses", help_text=(
      "A list of usernames of graders for the course who are allowed to edit the rubric."))
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
      ('portkey', 'Portkey (Self-hosted)'),
      ('custom', 'Custom Provider'),
  ]
  ai_provider = models.CharField(
      max_length=32,
      blank=True,
      null=True,
      choices=AI_PROVIDER_CHOICES,
      help_text="AI provider for comment generation"
  )


  ai_api_key = EncryptedCharField(
      max_length=512,
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
  ai_disabled = models.BooleanField(
      default=False,
      help_text="If True, all AI features are disabled even if configured"
  )
  ai_comments_disabled = models.BooleanField(
      default=False,
      help_text="If True, AI comment generation is disabled even if AI is globally enabled"
  )
  ai_chat_disabled = models.BooleanField(
      default=False,
      help_text="If True, AI chat assistant is disabled even if AI is globally enabled"
  )
  ai_use_own_settings = models.BooleanField(
      default=False,
      help_text="If True, course uses its own AI settings instead of the organization's configuration"
  )
  ai_token_rates = JSONField(
      default=dict, blank=True,
      help_text='Custom per-model token rates. JSON object mapping model names to {"input": <$/1M tokens>, "output": <$/1M tokens>}'
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

  gradersCanEditSubmissions = models.BooleanField(default=False, help_text=(
      "A boolean field. If True, graders will be allowed to edit student submissions (e.g. for testing fixes)."))
  
  runFilesOnSubmit = models.BooleanField(default=True, help_text=(
      "If True, submission files will be automatically executed and cached when a student submits."))

  runTestsOnSubmit = models.BooleanField(default=True, help_text=(
      "If True, autograder tests will automatically run when a student submits."))
  
  testsAffectGrade = models.BooleanField(default=True, help_text=(
      "If True, the results of autograder tests will be included in the submission grade calculation."))

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
    # Always recalculate grade when not frozen (allows tests to affect grade before finalization)
    if not self.gradeFrozen:
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
    data: models.TextField[str, str]
    name: models.CharField[str, str]
    extension: models.CharField[str, str]
  
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
      if name in ['_handler', 'handler', 'code']:
          raise AttributeError(name)
          
      try:
          return getattr(self.handler, name)
      except AttributeError:
          raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

  def save(self, *args, **kwargs):
    # Check if trying to use deprecated 'code' field
    if hasattr(self, 'code') and self.code:  # type: ignore[attr-defined]
      raise Exception("File.code is deprecated. Use File.data instead.")
 
    # Normalize newlines, but only for text files
    BINARY_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg']
    if not any(self.extension.lower().endswith(ext) for ext in BINARY_EXTENSIONS):
        if '\\r\\n' in self.data:
            self.data = self.data.replace("\\r\\n", "\\n")
    
    # Ensure utf-8 encoding (base64 is ascii safe)
    self.data = self.data.encode('utf-8').decode('utf-8')
    self.hash = hashlib.sha256(self.data.encode('utf-8')).hexdigest()
    
    # Infer extension from name if not provided
    if not self.extension:
      match = re.search(r'(\.[^.]+)$', self.name)
      if match:
        self.extension = match.group(1)
      else:
        # extension is required for text files
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
  
  hidden = models.BooleanField(
    default=False,
    help_text=("If True, this dataset will be hidden from students."))

  # Whether this dataset is a test resource (linked to a TestCategory)
  is_test_resource = models.BooleanField(
      default=False,
      help_text="If True, this dataset is used as a resource for a TestCategory.")

  course = property(lambda self: self.assignment.course)
  
  def save(self, *args, **kwargs):
    # Test resources should never be student-visible.
    if self.is_test_resource:
      self.hidden = True

    # Set default mount_path if not provided
    if not self.mount_path and self.name:
      # Sanitize name for filesystem use - keep dots for file extensions
      safe_name = self.name.lower().replace(' ', '_')
      safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-.')
      self.mount_path = f'shared/{safe_name}'
    
    super(AssignmentDataSet, self).save(*args, **kwargs)
  
  def delete(self, *args, **kwargs):
    # Delete the file from disk when the dataset is deleted
    if self.file:
      try:
        self.file.delete(save=False)
      except Exception:
        pass  # File might not exist or be inaccessible
    super(AssignmentDataSet, self).delete(*args, **kwargs)
  
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
    
    # Get file content - File subclasses use 'data'
    file_content = getattr(file, 'data', None) or ''
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
    output_data = self.output_data
    success = True
    stdout = None
    stderr = None
    error = None
    system_logs = None
    tests = None
    execution_time = self.execution_time_seconds

    # If cached output_data looks like ExecutionResult.to_dict(), unwrap and promote fields
    if isinstance(output_data, dict):
      if any(key in output_data for key in ("stdout", "stderr", "error", "success", "output_data")):
        success = output_data.get("success", True)
        stdout = output_data.get("stdout")
        stderr = output_data.get("stderr")
        error = output_data.get("error")
        system_logs = output_data.get("system_logs")
        tests = output_data.get("tests")
        if output_data.get("execution_time") is not None:
          execution_time = output_data.get("execution_time")

        # Prefer the inner output_data if present (matches fresh execution response shape)
        if output_data.get("output_data") is not None:
          output_data = output_data.get("output_data")

    response_data = {
        "success": success,
        "output_data": output_data,
        "file_id": file.id,
        "file_name": file.name,
        "error": error,
        "execution_time": execution_time,
        "cached": True,
        "executed_at": self.executed_at.isoformat(),
        "executed_by": self.executed_by.username if self.executed_by else None,
    }

    if stdout is not None:
      response_data["stdout"] = stdout
    if stderr is not None:
      response_data["stderr"] = stderr
    if system_logs is not None:
      response_data["system_logs"] = system_logs
    if tests is not None:
      response_data["tests"] = tests
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
    
    # Get file content - File subclasses use 'data'
    file_content = getattr(file, 'data', None) or ''
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
  
  hidden = models.BooleanField(
    default=False,
    help_text=("If True, this file will be hidden from students (but available for tests/helpers)."))
  
  # Whether this file is a test resource (linked to a TestCategory)
  is_test_resource = models.BooleanField(
      default=False,
      help_text="If True, this file is used as a resource for a TestCategory.")
  isVisible = property(lambda self: self.assignment.isVisible)

  course = property(lambda self: self.assignment.course)

  def save(self, *args, **kwargs):
    # Test resources should never be student-visible.
    if self.is_test_resource:
      self.hidden = True
    return super(AssignmentFile, self).save(*args, **kwargs)


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
  __test__ = False

  if TYPE_CHECKING:
    id: int
    assignment: Assignment
    testCases: RelatedManager[TestCase]

  assignment: Assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,  # type: ignore[assignment]
                                 related_name="testCategories", help_text=("The related assignment__id."))
  name = models.CharField(max_length=48, help_text=("The name of the test."))
  
  testScript = models.TextField(blank=True, default="", help_text=("Python script containing @test decorated functions."))
  maxPoints = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text=("Total points available for this category."))
  sortKey = models.IntegerField(default=0, help_text=("Integer to specify the order of display."))
  targetFileName = models.CharField(max_length=255, null=True, blank=True, help_text="The name of the file this test targets.")
  
  course = property(lambda self: self.assignment.course)

  class Meta:
    unique_together = ('name', 'assignment')

testTypes = (
    ('io', 'io'),
    ('io_cli', 'io_cli'),
    ('unit', 'unit'),
    ('shell', 'shell'),
    ('file', 'file'),
    ('external', 'external'),
    ('script', 'script'),)

testCase_status_types = (
    (0, 'Passed'),
    (1, 'Failed'),
    (2, 'Error'),
    (3, 'Never run'),
)


class TestCase(BaseModel):
  __test__ = False

  if TYPE_CHECKING:
    id: int
    testCategory: TestCategory
    instances: RelatedManager[SubmissionTest]

  testCategory: TestCategory = models.ForeignKey(TestCategory, on_delete=models.CASCADE,  # type: ignore[assignment]
                                   related_name="testCases", help_text=("The related testCategory__id."))
  sortKey = models.IntegerField(default=0, help_text=(
      "Integer to specify the order of a Assignment's Tests."))
  description = models.CharField(max_length=255, help_text=("Test description."))
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
  
  rubricItem = models.ForeignKey(RubricComment, null=True, blank=True, on_delete=models.SET_NULL, help_text=("The related rubric comment. If set, failure applies this rubric item."))

  functionName = models.CharField(max_length=128, blank=True, null=True, help_text=("The name of the function in the test script."))

  ################# Script / Notebook / Robust Framework Fields ########################
  # Field for custom test scripts (type='script')
  testCode = models.TextField(blank=True, help_text=("The custom test script code."))
  targetCellId = models.CharField(max_length=64, blank=True, null=True, help_text=("The ID of the notebook cell to target for execution."))
  timeout = models.IntegerField(default=30, help_text=("Execution timeout in seconds for this test."))

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
  results = models.JSONField(null=True, blank=True, help_text=(
      "Structured test results (list of subtests)."))
  score = models.DecimalField(max_digits=7, decimal_places=2, default=0, help_text=(
      "Aggregate score earned from all subtests."))
  maxScore = models.DecimalField(max_digits=7, decimal_places=2, default=0, help_text=(
      "Maximum possible score from all subtests."))

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
  if submission.pk is None:
    if submission.assignment.additiveGrading:
      return Decimal(0)
    else:
      return Decimal(submission.assignment.points)

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
  counter = Decimal(0)
  if submission.assignment.testsAffectGrade:
    tests = getLatestSubmissionTests(submission)
    for test in tests:
      # Use stored earned score directly when maxScore is present.
      # This is robust for partial-credit script tests even if pointsPass
      # metadata is stale or zero due to parsing mismatches.
      if test.maxScore and test.maxScore > 0:
        earned = Decimal(test.score)
        max_possible = Decimal(test.maxScore)
        if earned < 0:
          earned = Decimal(0)
        if earned > max_possible:
          earned = max_possible
        counter += earned
      else:
        # Fallback to binary pass/fail for legacy tests
        if test.passed:
          counter += Decimal(test.testCase.pointsPass)
        else:
          counter += Decimal(test.testCase.pointsFail)

  # Reduce to deduction
  if submission.assignment.additiveGrading:
    return Decimal(-1 * sum(deductions.values()) + counter)
  else:
    return Decimal(submission.assignment.points) - Decimal(sum(deductions.values())) + counter


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


class TestCategoryResource(BaseModel):
  __test__ = False

  if TYPE_CHECKING:
    id: int
    category: models.ForeignKey[TestCategory, TestCategory]
    file: Optional[models.ForeignKey[AssignmentFile, AssignmentFile]]
    dataset: Optional[models.ForeignKey[AssignmentDataSet, AssignmentDataSet]]

  category = models.ForeignKey("TestCategory", on_delete=models.CASCADE, related_name="resources", help_text="The related test category.")
  
  # A resource can be either a File or a DataSet
  file = models.ForeignKey("AssignmentFile", on_delete=models.CASCADE, null=True, blank=True, help_text="The source file.")
  dataset = models.ForeignKey("AssignmentDataSet", on_delete=models.CASCADE, null=True, blank=True, help_text="The source dataset.")
  
  # The path/name this resource will have in the test environment (Aliasing)
  target_path = models.CharField(max_length=512, help_text="The filename or path this resource will be saved as during test execution. Allows aliasing (e.g. use 'test1.txt' as 'input.txt').")

  def save(self, *args, **kwargs):
    if not self.file and not self.dataset:
      raise ValidationError("A TestCategoryResource must have either a file or a dataset.")
    if self.file and self.dataset:
      raise ValidationError("A TestCategoryResource cannot have both a file and a dataset.")

    # Automatically tag the linked resource as a test resource
    if self.file:
      self.file.is_test_resource = True 
      self.file.save()
    if self.dataset:
      self.dataset.is_test_resource = True
      self.dataset.save()

    super(TestCategoryResource, self).save(*args, **kwargs)

  class Meta:
    unique_together = [
        ('category', 'target_path') # Ensure no two resources try to write to the same path
    ]

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


@receiver(post_save, sender=SubmissionTest)
def save_submission_from_test(sender, instance, **kwargs):
  """Trigger grade recalculation when test results change."""
  instance.submission.save()


@receiver(post_delete, sender=SubmissionTest)
def save_submission_from_test_delete(sender, instance, **kwargs):
  """Trigger grade recalculation when test results are deleted."""
  try:
    instance.submission.save()
  except Submission.DoesNotExist:
    pass


@receiver(post_save, sender=TestCategory)
def update_test_cases_from_script(sender, instance, **kwargs):
    """Parse test script and update TestCases on save."""
    import logging
    _logger = logging.getLogger(__name__)
    try:
        from autograder.services.TestParsingService import TestParsingService
        TestParsingService.update_test_cases(instance)
    except Exception as e:
        _logger.exception(f"Failed to update test cases for TestCategory {instance.pk}: {e}")


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


class CommentTemplate(BaseModel):
  if TYPE_CHECKING:
    id: int
    owner: models.ForeignKey[User, User]
    assignment: models.ForeignKey[Assignment, Assignment]
    rubricComment: Optional[models.ForeignKey[RubricComment, RubricComment]]
    sourceComment: Optional[models.ForeignKey[Comment, Comment]]

  text = models.TextField(help_text=("The text of the template."))
  owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comment_templates", help_text=("The creator of the template."))
  assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="comment_templates", help_text=("The assignment this template belongs to."))
  isGlobal = models.BooleanField(default=False, help_text=("If True, this template is visible to all graders in the assignment."))
  cellId = models.CharField(max_length=36, null=True, blank=True, help_text=("Optional notebook cell ID. If set, template only shows for this cell."))
  filePath = models.CharField(max_length=500, null=True, blank=True, help_text=("Optional file path pattern. If set, template only shows for matching files."))
  
  pointDelta = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, help_text=("Points delta for this template."))
  rubricComment = models.ForeignKey('RubricComment', null=True, blank=True, on_delete=models.SET_NULL, related_name="templates", help_text=("Optional linked rubric comment."))
  sourceComment = models.ForeignKey('Comment', null=True, blank=True, on_delete=models.SET_NULL, related_name="derived_templates", help_text=("The original comment this template was created from. Null if manually created or source was deleted."))

  def __str__(self):
    return self.text[:20] + "..."

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
    "CommentTemplate",
    "MaintenanceBanner",
]


class MaintenanceBanner(models.Model):
    """
    Singleton model — always use pk=1.
    Controls the maintenance banner shown to all frontend users.
    Manage via Django admin (/admin/).

    Schedule fields (both optional):
    - starts_at: banner only shows after this UTC datetime (None = show immediately)
    - ends_at:   banner auto-hides after this UTC datetime (None = no expiry)

    active_now() factors in both the manual toggle and the schedule window.
    """

    SEVERITY_INFO = "info"
    SEVERITY_WARNING = "warning"
    SEVERITY_CRITICAL = "critical"
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, "Info"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_CRITICAL, "Critical"),
    ]

    active = models.BooleanField(default=False, help_text="Manually enable/disable the banner.")
    message = models.TextField(
        default="codePost is currently undergoing maintenance. Some features may be unavailable.",
        help_text="The message displayed in the banner.",
    )
    color = models.CharField(
        max_length=30,
        default="#0e704c",
        help_text="Background colour (any CSS value, e.g. #0e704c or red).",
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_INFO,
        help_text="Visual severity of the banner (affects the icon shown to users).",
    )
    starts_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="If set, the banner will not appear before this UTC time even when active=True.",
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="If set, the banner auto-hides after this UTC time.",
    )

    class Meta:
        verbose_name = "Maintenance Banner"
        verbose_name_plural = "Maintenance Banner"

    def save(self, *args, **kwargs):
        # Force singleton: always pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "MaintenanceBanner":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def is_active_now(self) -> bool:
        """True only when the manual toggle is on AND within the optional schedule window."""
        if not self.active:
            return False
        from django.utils import timezone
        now = timezone.now()
        if self.starts_at is not None and now < self.starts_at:
            return False
        if self.ends_at is not None and now > self.ends_at:
            return False
        return True

    def __str__(self):
        status = "ACTIVE" if self.active else "inactive"
        return f"MaintenanceBanner [{status}]"


class AIUsageRecord(BaseModel):
  """Tracks individual AI API calls for usage reporting and cost estimation."""
  if TYPE_CHECKING:
    id: int

  REQUEST_TYPE_CHOICES = [
      ('comment_generation', 'Comment Generation'),
      ('code_review', 'Code Review'),
      ('feedback', 'Feedback'),
      ('other', 'Other'),
  ]

  organization = models.ForeignKey(
      Organization, on_delete=models.SET_NULL, null=True, blank=True,
      related_name='ai_usage_records',
      help_text="The organization associated with this usage record"
  )
  course = models.ForeignKey(
      'Course', on_delete=models.SET_NULL, null=True, blank=True,
      related_name='ai_usage_records',
      help_text="The course associated with this usage record"
  )
  assignment = models.ForeignKey(
      'Assignment', on_delete=models.SET_NULL, null=True, blank=True,
      related_name='ai_usage_records',
      help_text="The assignment associated with this usage record"
  )
  user = models.ForeignKey(
      User, on_delete=models.SET_NULL, null=True, blank=True,
      related_name='ai_usage_records',
      help_text="The user who triggered this AI request"
  )
  provider = models.CharField(
      max_length=32, help_text="AI provider used (e.g., openai, gemini)"
  )
  model = models.CharField(
      max_length=64, help_text="Model name used for this request"
  )
  request_type = models.CharField(
      max_length=32, choices=REQUEST_TYPE_CHOICES, default='other',
      help_text="Type of AI request"
  )
  input_tokens = models.PositiveIntegerField(
      default=0, help_text="Number of input/prompt tokens"
  )
  output_tokens = models.PositiveIntegerField(
      default=0, help_text="Number of output/completion tokens"
  )
  total_tokens = models.PositiveIntegerField(
      default=0, help_text="Total tokens (input + output)"
  )
  cached_tokens = models.PositiveIntegerField(
      default=0, help_text="Number of input tokens served from provider cache (reduced cost)"
  )
  estimated_cost = models.DecimalField(
      max_digits=10, decimal_places=6, default=Decimal('0'),
      help_text="Estimated cost in USD for this API call"
  )
  status = models.CharField(
      max_length=16, default='success',
      help_text="Status of the request: success, error"
  )
  error_message = models.TextField(
      blank=True, null=True,
      help_text="Error message if the request failed"
  )

  class Meta:
    ordering = ('-created',)
    indexes = [
        models.Index(fields=['organization', 'created']),
        models.Index(fields=['course', 'created']),
        models.Index(fields=['assignment', 'created']),
        models.Index(fields=['created']),
    ]

  def __str__(self):
    return f"AIUsage [{self.provider}/{self.model}] {self.total_tokens} tokens"


###############################################################################
# Chat Conversations (Agentic Grading Assistant)
###############################################################################

class ChatConversation(BaseModel):
  """A chat conversation thread between a grader and the AI assistant."""
  if TYPE_CHECKING:
    id: int

  submission = models.ForeignKey(
      'Submission', on_delete=models.CASCADE,
      related_name='chat_conversations',
      help_text="The submission this conversation is about",
  )
  assignment = models.ForeignKey(
      'Assignment', on_delete=models.CASCADE,
      related_name='chat_conversations',
      help_text="The assignment this conversation belongs to",
  )
  user = models.ForeignKey(
      User, on_delete=models.CASCADE,
      related_name='chat_conversations',
      help_text="The grader who owns this conversation",
  )
  title = models.CharField(
      max_length=200, blank=True, default='',
      help_text="Title for this conversation (auto-generated or user-set)",
  )
  summary = models.TextField(
      blank=True, default='',
      help_text="Rolling summary of older messages for context window management",
  )

  class Meta:
    ordering = ('-modified',)
    indexes = [
        models.Index(fields=['submission', 'user']),
        models.Index(fields=['assignment', 'user']),
    ]

  def __str__(self):
    return f"Chat [{self.id}] {self.user} on Submission {self.submission_id}"


class ChatMessage(BaseModel):
  """A single message in a chat conversation."""
  if TYPE_CHECKING:
    id: int

  ROLE_CHOICES = [
      ('user', 'User'),
      ('assistant', 'Assistant'),
      ('tool_call', 'Tool Call'),
      ('tool_result', 'Tool Result'),
      ('summary', 'Summary'),
  ]

  TOOL_STATUS_CHOICES = [
      ('pending', 'Pending'),
      ('approved', 'Approved'),
      ('rejected', 'Rejected'),
  ]

  conversation = models.ForeignKey(
      ChatConversation, on_delete=models.CASCADE,
      related_name='messages',
      help_text="The conversation this message belongs to",
  )
  role = models.CharField(
      max_length=16, choices=ROLE_CHOICES,
      help_text="Who sent this message",
  )
  content = models.TextField(
      blank=True, default='',
      help_text="The message text content",
  )
  tool_name = models.CharField(
      max_length=64, blank=True, null=True,
      help_text="Name of the tool (for tool_call/tool_result roles)",
  )
  tool_args = models.JSONField(
      blank=True, null=True,
      help_text="JSON arguments for the tool call",
  )
  tool_status = models.CharField(
      max_length=16, choices=TOOL_STATUS_CHOICES,
      blank=True, null=True,
      help_text="Whether the tool call was approved or rejected by the user",
  )
  token_count = models.PositiveIntegerField(
      default=0,
      help_text="Number of tokens in this message",
  )

  class Meta:
    ordering = ('created',)
    indexes = [
        models.Index(fields=['conversation', 'created']),
    ]

  def __str__(self):
    return f"ChatMsg [{self.role}] in Conversation {self.conversation_id}"
