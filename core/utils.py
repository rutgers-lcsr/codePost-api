from django.http import HttpRequest
from core.serializers.user import UserSerializer
from core.models import Assignment, Course, RubricCategory, Environment, TestCategory
from django.template import loader
from django.core.mail import EmailMultiAlternatives
from django.core.exceptions import ObjectDoesNotExist

# Import User from django but get type annotations from core.models
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.models import User
else:
    from django.contrib.auth.models import User

import re
import structlog
from typing import Optional, Dict, Any

logger = structlog.get_logger(__name__)

def my_jwt_response_handler(token: str, user: Optional[User] = None, request: Optional[HttpRequest] = None) -> Dict[str, Any]:
  """ Custom response payload handler for JWT authentication
  This function returns the response data after login or token refresh
  """
  # if we don't do this, then the UserSerializer won't be able to access the requesting user.
  # why? because the *request to authenticate* doesn't contain an authenticated user
  if request is not None:
    request.user = user

  return {
      'token': token,
      'user': UserSerializer(user, context={'request': request}).data
  }

def is_course_member(user: User) -> bool:
  if len(user.student_courses.all()) > 0:
    return True

  if len(user.grader_courses.all()) > 0:
    return True

  if len(user.courseAdmin_courses.all()) > 0:
    return True

  if len(user.student_inactive_courses.all()) > 0:
    return True

  if len(user.grader_inactive_courses.all()) > 0:
    return True

  if len(user.courseAdmin_inactive_courses.all()) > 0:
    return True

  return False


def is_email(email: str) -> bool:
  if len(email) > 7:
    if re.match(r"[^@]+@[^@]+\.[^@]+", email):
      return True
  return False


def email_passes_whitelist(email: str, whitelist: str) -> bool:
  if len(whitelist) == 0:
    return True

  valid_domains = whitelist.split("\n")
  email_domain = email.split('@')[1]
  for domain in valid_domains:
    if domain == email_domain:
      return True

  return False

def get_or_create_user(email: str, organization: Any, auto_activate: bool = False) -> Optional[User]:
  """ If a user corresponds to <email>, return that user. Else,
  create a user with <email> and set their organization to <organization> """

  if is_email(email):
    try:
      thisUser = User.objects.get(email=email)
      return thisUser
    except User.DoesNotExist:
      # Check if organization supports SSO auto-activation
      # If so, we auto-activate the user so they can get an OTT immediately
      sso_activate = False
      if organization and hasattr(organization, 'sso_enabled') and organization.sso_enabled:
          sso_activate = True

      newUser = User.objects.create(username=email, email=email, is_active=auto_activate or sso_activate)
      newUser.profile.organization = organization
      newUser.profile.isPasswordSet = False
      newUser.save()
      return newUser
  else:
    return None


def send_mail(subject_template_name: str, email_template_name: str,
              context: Dict[str, Any], from_email: str, to_email: str, 
              html_email_template_name: Optional[str] = None) -> None:
  """
  Send a django.core.mail.EmailMultiAlternatives to `to_email`.
  """
  subject = loader.render_to_string(subject_template_name, context)
  subject = ''.join(subject.splitlines())
  body = loader.render_to_string(email_template_name, context)

  email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
  if html_email_template_name is not None:
    html_email = loader.render_to_string(html_email_template_name, context)
    email_message.attach_alternative(html_email, 'text/html')

  logger.info("sending_email", to=to_email, subject=subject, from_email=from_email)
  email_message.send()


def domain_from_email(email: str) -> str:
  return '@' + email.split('@')[1]

def copy_assignment(assignment: Assignment, destination_course: Course) -> Optional[Assignment]:
  new_assignment = assignment
  original_assignment = Assignment.objects.get(id=assignment.id)

  course_assignments = Assignment.objects.filter(course=destination_course.id).values_list('name', flat=True)

  # Only add "(copy N)" suffix if there's a name collision in the destination course
  new_name = new_assignment.name
  if new_name in course_assignments:
    count = 1
    new_name = f"{new_assignment.name} (copy {count})"

    # Prevent copying the same assignment into the same course more than 10 times
    while new_name in course_assignments and count < 10:
      count += 1
      new_name = f"{new_assignment.name} (copy {count})"

    if count == 10:
      return None

  # copy assignment
  new_assignment.id = None  # type: ignore[assignment]
  new_assignment.pk = None
  new_assignment.name = new_name
  new_assignment.course_id = destination_course.id  # type: ignore[attr-defined]

  # Reset student-facing settings for safety when cloning to a new course
  new_assignment.isReleased = False
  new_assignment.isVisible = False
  new_assignment.feedbackReleased = False
  new_assignment.liveFeedbackMode = False

  # Reset dates
  new_assignment.uploadDueDate = None
  new_assignment.regradeDeadline = None

  # Reset stats
  new_assignment.mean = None
  new_assignment.median = None

  # Copy AI settings
  new_assignment.ai_system_prompt = original_assignment.ai_system_prompt

  new_assignment.save()

  # copy assignment files (template files)
  from core.models import AssignmentFile, AssignmentDataSet, TestCase as AssignmentTestCase, TestCategoryResource
  from django.core.files.base import ContentFile

  assignment_file_map = {}
  for assignmentFile in original_assignment.files.all():
    # Create new file with same data
    new_file = AssignmentFile.objects.create(
      assignment=new_assignment,
      name=assignmentFile.name,
      data=assignmentFile.data,
      extension=assignmentFile.extension,
      path=assignmentFile.path,
      required=assignmentFile.required,
      description=assignmentFile.description,
      hidden=assignmentFile.hidden,
      is_test_resource=assignmentFile.is_test_resource,
    )
    assignment_file_map[assignmentFile.id] = new_file

  # copy rubric
  for rubricCategory in original_assignment.rubricCategories.all():
    original_rubricCategory = RubricCategory.objects.get(id=rubricCategory.id)
    new_rubricCategory = RubricCategory.objects.create(
      assignment=new_assignment,
      name=rubricCategory.name,
      pointLimit=rubricCategory.pointLimit,
      helpText=rubricCategory.helpText,
      sortKey=rubricCategory.sortKey
    )
    for rubricComment in original_rubricCategory.rubricComments.all():
      rubricComment.pk = None
      rubricComment.category = new_rubricCategory
      rubricComment.save()

  try:
    environment = original_assignment.environment
  except ObjectDoesNotExist:
    environment = None

  if environment is not None:
    Environment.objects.create(
      assignment=new_assignment,
      language=environment.language,
      buildType=environment.buildType,
      dockerfile=environment.dockerfile,
      dockerRunInstructions=environment.dockerRunInstructions,
      compileText=environment.compileText,
      allowNetworkAccess=environment.allowNetworkAccess,
      maxStudentTestRuns=environment.maxStudentTestRuns,
      maxExposedFailedTests=environment.maxExposedFailedTests,

      # Custom environment fields
      image_name=environment.image_name,  # Reuse image to avoid rebuild
      build_status=environment.build_status,  # Keep status if we reuse image
      requirements=environment.requirements,
      env_vars=environment.env_vars,
      auto_detect=environment.auto_detect
    )

  # Copy DataSets
  dataset_map = {}
  for dataset in original_assignment.dataSets.all():
    # We must duplicate the file content so the new dataset has its own file
    if dataset.file:
      new_dataset = AssignmentDataSet(
        assignment=new_assignment,
        name=dataset.name,
        description=dataset.description,
        mount_path=dataset.mount_path,
        is_active=dataset.is_active,
        hidden=dataset.hidden,
        is_test_resource=dataset.is_test_resource,
      )
      # Read original file and save to new dataset
      # This creates a new physical file in storage
      try:
        with dataset.file.open('rb') as f:
          new_dataset.file.save(dataset.file.name, ContentFile(f.read()), save=False)
        new_dataset.save()
        dataset_map[dataset.id] = new_dataset
      except Exception as e:
        logger.error(f"Failed to clone dataset {dataset.id}: {e}")

  # copy tests (including test scripts and linked resources)
  for testCategory in original_assignment.testCategories.all():
    original_testCategory = TestCategory.objects.get(id=testCategory.id)
    new_testCategory = TestCategory.objects.create(
      assignment=new_assignment,
      name=testCategory.name,
      testScript=testCategory.testScript,
      maxPoints=testCategory.maxPoints,
      sortKey=testCategory.sortKey,
      targetFileName=testCategory.targetFileName,
    )

    for testCase in original_testCategory.testCases.all():
      AssignmentTestCase.objects.create(
        testCategory=new_testCategory,
        sortKey=testCase.sortKey,
        description=testCase.description,
        type=testCase.type,
        pointsFail=testCase.pointsFail,
        pointsPass=testCase.pointsPass,
        text=testCase.text,
        explanation=testCase.explanation,
        exposed=testCase.exposed,
        lastSolutionRun=testCase.lastSolutionRun,
        rubricItem=testCase.rubricItem,
        functionName=testCase.functionName,
        testCode=testCase.testCode,
        targetCellId=testCase.targetCellId,
        timeout=testCase.timeout,
      )

    for resource in original_testCategory.resources.all():
      cloned_file = assignment_file_map.get(resource.file_id) if resource.file_id else None
      cloned_dataset = dataset_map.get(resource.dataset_id) if resource.dataset_id else None

      if not cloned_file and not cloned_dataset:
        logger.warning(
          "Skipping clone of test resource %s for category %s because source file/dataset was not cloned",
          resource.id,
          original_testCategory.id,
        )
        continue

      TestCategoryResource.objects.create(
        category=new_testCategory,
        file=cloned_file,
        dataset=cloned_dataset,
        target_path=resource.target_path,
      )

  return new_assignment

