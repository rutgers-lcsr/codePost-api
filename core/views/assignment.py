from datetime import timedelta
from typing import TYPE_CHECKING
from core.logging import logEvent
from core.models import Assignment, AssignmentFile, RubricCategory, RubricComment, TestCase, Submission, Course, SubmissionFile
from rest_framework import serializers
from rest_framework.request import Request
from core.serializers.assignment import AssignmentSerializer, AssignmentSerializerWithStatistics, AssignmentStudentSerializer, AssignmentSerializerWithStatisticsAndSummary, AssignmentStudentSerializerNoStats, AssignmentStudentSerializerWithStats
from core.serializers.submission import AnonymousSubmissionSerializer, SubmissionSerializer, StudentSubmissionSerializer, StudentSubmissionWithoutGradeSerializer, SubmissionSerializerWithoutFiles, SubmissionWithTestsSerializer
from core.serializers.rubricCategory import RubricCategorySerializer, RubricCategoryStudentSerializer
from core.serializers.rubricComment import RubricCommentSerializer
from core.serializers.submissionHistory import SubmissionHistorySerializer
from core.serializers.comment import CommentSerializer

from core.serializers.testCase import TestCaseStudentSerializer
from core.serializers.testCategory import TestCategorySerializer
from core.serializers.file import FileValidationSerializerWithoutSubmission, SubmissionFileStudentUploadSerializer


from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from core.models import Section, SubmissionHistory, Comment

from core.views.template import ListProtectedViewSet

from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from core.pagination import DefaultPagination, LargeObjectsPagination


from core.permissions.permissions import AssignmentPermissions, RubricCommentPermissions
from core.permissions.helpers import returnNotAuthorized, returnForbidden, returnNotFound, returnInvalid
from core.permissions.helpers import isAuthenticated
from core.permissions.helpers import isStudent, isGrader, isCourseAdmin, isCourseMember, isCourseStaff, isSuperGrader, canViewUnanonymizedSubmissions
from core.permissions.helpers import isStudentOfSub, isStaffOfSub

from django.utils.timezone import now

from django.db.models import Q

from core.utils import copy_assignment
from core.handlers.late_submission_handler import LateSubmissionHandler
import io
import zipfile
import base64
from core.emails import StudentUploadReceiptEmail

import logging
logger = logging.getLogger(__name__)

def encoded_zip(files: list[AssignmentFile]) -> str:
  """
  Create zip from files in memory
  """
  zip_buffer = io.BytesIO()

  with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
    for file in files:
      zip_file.writestr(file.name, file.data)

  return base64.b64encode(zip_buffer.getvalue()).decode()


class AssignmentViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the assignments.

  create:
  Create a new assignment instance.

  retrieve:
  Return the given assignment.

  update:
  Update an assignment.

  partial_update:
  Update an assignment.

  delete:
  Delete an assignment
  """
  if TYPE_CHECKING:
    request: Request
  
  queryset = Assignment.objects.all()
  permission_classes = (IsAuthenticated, AssignmentPermissions)
  serializer_class = AssignmentSerializer

  def get_object(self) -> Assignment:
    return super().get_object()

  # return an assignment serializer with statistics if the user is allowed to see them
  def get_serializer_class(self):
    if self.action == 'retrieve':
      user = self.request.user
      assignment = self.get_object()
      course = assignment.course

      if isCourseAdmin(user, course):
        return AssignmentSerializerWithStatisticsAndSummary

      # if a grader who isn't an admin, return without statistics
      elif isGrader(user, course):
        return AssignmentSerializer

      # user is a student only
      else:
        if (not assignment.isReleased and not assignment.liveFeedbackMode):
          return AssignmentStudentSerializer
        elif (not course.showStudentsStatistics):
          return AssignmentStudentSerializerNoStats
        else:
          return AssignmentStudentSerializerWithStats
    else:
      return AssignmentSerializer

  # Extra functions
  #####################################################################################

  @action(detail=True)
  def comments(self, request, pk=None):
    """
    Grab all custom comments applied to submissions for this assignment, possibly filtered by
    author

    FIXME: we should make this endpoint more generic by optionally filtering based on .rubricComment,
    instead of filtering out comments s.t. rubricComment = None by default.
    """
    user = self.request.user
    assignment = self.get_object()
    course = assignment.course

    # are we filtering by author?
    author = self.request.query_params.get('author', None)

    if author:
      if (self.request.user.email == author) or isCourseAdmin(user, course) or isSuperGrader(user, course):
        comments = Comment.objects.filter(file__submission__assignment=assignment,
                                          author__email=author, rubricComment=None)
      else:
        return returnForbidden()
    else:
      if isCourseAdmin(user, course) or isSuperGrader(user, course):
        comments = Comment.objects.filter(file__submission__assignment=assignment, rubricComment=None)
      else:
        return returnForbidden()

    serial = CommentSerializer(comments, many=True, context={'request': request})

    return Response(serial.data)

  @action(detail=True)
  def queueLength(self, request, pk=None):
    """
    Show the rubric for this assignment.
    """
    user = self.request.user
    assignment = self.get_object()
    course = assignment.course

    # Only graders can view the queue length
    if not isGrader(user, course):
      return returnForbidden()

    section = self.request.query_params.get('section', None)
    
    # Base query: submissions for this assignment that are unassigned
    # We also filter for students enrolled in the course
    if isCourseAdmin(user, course):
      submissions = assignment.submissions.filter(
          grader=None, students__in=course.students.all())
    else:
      submissions = assignment.submissions.filter(
          ~Q(students__in=[user]), grader=None, students__in=course.students.all())

    # Apply section filter if provided
    # Note: query param 'section' can be a list if multiple sections are selected?
    # The frontend code sends params.append('section', id) multiple times for multiple sections
    # Django's request.query_params.getlist('section') should be used if we support multiple
    # but the frontend code: 
    # params.append('section', section.id.toString());
    # implies we might get multiple sections.
    # However, let's look at how drawUnassigned handles it. 
    # drawUnassigned: section = self.request.query_params.get('section', None)
    # it only handles ONE section.
    # Let's check the frontend again...
    
    # Frontend:
    # if (sections && sections.length > 0) {
    #   sections.forEach((section) => {
    #     params.append('section', section.id.toString());
    #   });
    # }
    
    # So potentially multiple 'section' keys.
    # But drawUnassigned only gets one: section = self.request.query_params.get('section', None)
    # The frontend claimSubmission logic calls fetchSubmission (which calls drawUnassigned) in a loop for each section.
    # BUT fetchQueueLength sends ALL sections at once.
    
    # So for queueLength, we should support multiple sections.
    
    sections = self.request.query_params.getlist('section')
    
    if sections:
        # Filter submissions that belong to any of the provided sections
        # Logic: submission -> students -> section
        # We want submissions where at least one student is in one of the provided sections
        
        # This can be complex if we need to verify section existence / course membership
        # effectively:
        # valid_sections = Section.objects.filter(id__in=sections, course=course)
        # submissions = submissions.filter(students__section__in=valid_sections).distinct()
        
        valid_sections = Section.objects.filter(id__in=sections, course=course)
        if valid_sections.exists():
            submissions = submissions.filter(students__student_sections__in=valid_sections).distinct()
    
    toRet = {
        'id': assignment.id,
        'unclaimed': submissions.count(),
        'finalized': assignment.submissions.filter(grader=user, isFinalized=True).count(),
        'unfinalized': assignment.submissions.filter(grader=user, isFinalized=False).count(),
    }

    return Response(toRet)

  # Returns the serialized rubric for this assignment
  @action(detail=True, permission_classes=((IsAuthenticated, RubricCommentPermissions)), methods=['GET'])
  def rubric(self, request, pk=None):
    """
    Show the rubric for this assignment.
    """
    user = self.request.user
    assignment = self.get_object()
    course = assignment.course

    categories = RubricCategory.objects.filter(assignment=assignment)

    if isCourseStaff(user, course):
      categorySerializer = RubricCategorySerializer(categories, many=True, context={'request': request})
    else:
      categorySerializer = RubricCategoryStudentSerializer(categories, many=True, context={'request': request})

    comments = RubricComment.objects.filter(category__assignment=assignment)
    commentSerializer = RubricCommentSerializer(comments, many=True, context={'request': request})

    toRet = {
        'id': assignment.id,
        'rubricCategories': categorySerializer.data,
        'rubricComments': commentSerializer.data,
    }

    return Response(toRet)

  @action(detail=True, methods=['GET'])
  def drawUnassigned(self, request, pk=None):
    """
    Get the next unassigned submission for this submission.
    """
    user = request.user
    assignment = self.get_object()
    course = assignment.course
    amount = self.request.query_params.get('amount', 1)

    if not isGrader(user, course):
      return returnForbidden()

    section = self.request.query_params.get('section', None)

    # Use system ordering to pull random unassigned submission
    # The students__in filter allows submissions to be claimed that *include* inactive students.
    # Examples: if submission.students = [active@uni.edu, inactive@uni.edu], the submission can be claimed
    #           if submission.students = [inactive@uni.edu], the submission can't be claimed
    #
    # To exclude submissions belonging to inactive students, regardless of the other students associated
    # with the submission, use .exclude(students__in=course.inactivestudents.all())
    if isCourseAdmin(user, course):
      submissions = assignment.submissions.filter(
          grader=None, students__in=course.students.all()).order_by('queueOrderKey')
    else:
      submissions = assignment.submissions.filter(
          ~Q(students__in=[user]), grader=None, students__in=course.students.all()).order_by('queueOrderKey')

    if section is not None:
      try:
        section = Section.objects.get(name=section, course=course)
        submissions = submissions.filter(students__in=section.students.all())
      except ObjectDoesNotExist:
        return returnNotFound(message="No such section")

    submission = None

    if len(submissions) <= 0:
      return Response(status=status.HTTP_204_NO_CONTENT)
     
    claimed_submissions = submissions[:int(amount)]
    
    for s in claimed_submissions:
      # Assign submission to grader
      # Doing this in this call is important, since it prevents two users from drawing the
      # save unassigned submission and subsequently trying to claim it
      s.grader = user
      s.save()
    


    serializerClass = SubmissionSerializer
    if assignment.anonymousGrading and not canViewUnanonymizedSubmissions(user, course):
      serializerClass = AnonymousSubmissionSerializer

    
    data = []
    # serializer = serializerClass(claimed_submissions, context={'request': request})
    
    for s in claimed_submissions:
      serializer = serializerClass(s, context={'request': request})
      data.append(serializer.data)

    return Response(data)

# Optional arguments: username, grader
# If neither specified, returns full list of submissions for this assignment
  @action(detail=True, pagination_class=DefaultPagination)
  def submissions(self, request, pk=None):
    """
    Return a (optionally filtered) list of submissions whose parent is the requested assignment.
    """

    # Gather variables
    user = request.user
    assignment = self.get_object()  # => this endpoint has permissions at least as strict
    course = assignment.course
    student = self.request.query_params.get('student', None)

    grader = self.request.query_params.get('grader', None)
    shouldReturnCompact = self.request.query_params.get('compact', None)
    submissions = assignment.submissions.all().prefetch_related('students', 'grader')
    shouldPaginate = self.request.query_params.get('page', None)

    #############################################################################################
    # Permissions assessment
    #############################################################################################
    isThisGrader = isGrader(user, course) and user.email == grader
    isThisStudent = isStudent(user, course) and user.email == student
    isCourseAdminCached = isCourseAdmin(user, course)

    # If you want to filter by grader, you must be that grader, courseadmin, or superGrader
    if grader is not None:
      if not isCourseAdminCached and not isSuperGrader(user, course) and not isThisGrader:
        return returnForbidden()

    # If you want all of the submissions, you must be a courseAdmin or superGrader
    if student is None and grader is None:
      if not isCourseAdminCached and not isSuperGrader(user, course):
        return returnForbidden()

    # If you want to filter by student, you must be a grader, courseAdmin, or that student
    if student is not None:
      if not isThisStudent and not isGrader(user, course) and not isCourseAdminCached:
        return returnForbidden()

    # If you want to use this endpoint and you are a student only, then you must wait until the assignment
    # is released, student upload is allowed, or live feedback mode is enabled
    isOnlyStudent = isThisStudent and not isThisGrader and not isCourseAdminCached
    if isOnlyStudent and not assignment.isReleased and not assignment.allowStudentUpload and not assignment.liveFeedbackMode:
      return returnForbidden()

    #############################################################################################

    # At this point, we can assume the client has the permissions necessary to perform the requested
    # action.

    # Retrieve student
    studentParam = None
    if student is not None:
      try:
        studentParam = User.objects.filter(Q(username=student) | Q(email=student)).first()
        if studentParam is None:
            raise User.DoesNotExist()
      except User.DoesNotExist:
        if isCourseAdmin(user, course):
          return returnNotFound(message="The user does not exist")
        else:
          return returnForbidden()

    # Retrieve grader
    graderParam = None
    if grader is not None:
      try:
        graderParam = User.objects.filter(Q(username=grader) | Q(email=grader)).first()
        if graderParam is None:
            raise User.DoesNotExist()
      except User.DoesNotExist:
        if isCourseAdmin(user, course):
          return returnNotFound(message="The user does not exist")
        else:
          return returnForbidden()

    # Perform filtering
    filteredSubs = None
    if studentParam is not None and graderParam is not None:
      filteredSubs = submissions.filter(students__in=[studentParam],
                                        grader=graderParam)
    elif studentParam is not None:
      filteredSubs = submissions.filter(students__in=[studentParam])
    elif graderParam is not None:
      filteredSubs = submissions.filter(grader=graderParam)
    else:
      filteredSubs = submissions

    # Client is only a student
    if isOnlyStudent:
      if len(filteredSubs) == 0:
        return Response([])

      subCandidate = filteredSubs[0]


      # StudentSubmissionSerializer handles all cases:
      # - Masks grade when feedbackReleased is False
      # - Returns files without comments when feedbackReleased is False
      # - Preserves real isFinalized status so frontend can show submission correctly
      serializer = StudentSubmissionSerializer(filteredSubs, many=True, context={'request': request})

    # Client has privilege that exceeds a student's
    else:
      if assignment.anonymousGrading and not canViewUnanonymizedSubmissions(user, course):
        serializer = AnonymousSubmissionSerializer(filteredSubs, many=True, context={'request': request})
      else:
        if shouldReturnCompact is not None and shouldReturnCompact != '0':
          if shouldPaginate:
            page = self.paginate_queryset(filteredSubs)
            if page is not None:
              serializer = SubmissionSerializerWithoutFiles(page, many=True)
              return self.get_paginated_response(serializer.data)
          serializer = SubmissionSerializerWithoutFiles(filteredSubs, many=True, context={'request': request})
        else:
          serializer = SubmissionSerializer(filteredSubs, many=True, context={'request': request})

    return Response(serializer.data)

  @action(detail=True, methods=['GET'], pagination_class=DefaultPagination)
  def submissionHistories(self, request: Request, pk=None):
    user = request.user
    assignment = self.get_object()  # => this endpoint has permissions at least as strict
    course = assignment.course
    shouldPaginate = self.request.query_params.get('page', None)


    # If not course admin or supergrader, return forbidden
    if not isCourseAdmin(user, course) and not isSuperGrader(user, course):
      return returnForbidden()
    submissionHistories = SubmissionHistory.objects.filter(submission__assignment=assignment)

    if shouldPaginate:
      page = self.paginate_queryset(submissionHistories)
      if page is not None:
        serializer = SubmissionHistorySerializer(page, many=True)
        return self.get_paginated_response(serializer.data)
    serializer = SubmissionHistorySerializer(submissionHistories, many=True, context={'request:': request})
    return Response(serializer.data)

  @action(detail=True, methods=["GET"])
  def studentTests(self, request, pk=None):
    #  Only accessed by students
    user = request.user
    assignment = self.get_object()

    if not isAuthenticated(user):
      return returnNotAuthorized()

    if not isCourseMember(user, assignment.course):
      return returnForbidden()

    # If user is the course admin or the assignment is in live feedback mode return all test cases
    # We need to return all tests for users that are course admin for the "See as student" view
    if isCourseAdmin(user, assignment.course) or assignment.liveFeedbackMode:
      test_cases = TestCase.objects.filter(testCategory__assignment=assignment)
    # If assignment is has been released and this endpoint has been called, check if the student's submission is finalized
    # If so, return all test cases. Else, return only exposed test cases
    elif assignment.isReleased:
      filteredSubs = Submission.objects.filter(assignment=assignment, students__in=[user])
      if len(filteredSubs) > 0 and filteredSubs[0].isFinalized:
        test_cases = TestCase.objects.filter(testCategory__assignment=assignment)
      else:
        test_cases = TestCase.objects.filter(testCategory__assignment=assignment, exposed=True).exclude(type="external")
    # If the assignment is not released or in live feedback mode, return only exposed test cases
    else:
      test_cases = TestCase.objects.filter(testCategory__assignment=assignment, exposed=True).exclude(type="external")

    test_categories = list(set(map(lambda test_case: test_case.testCategory, test_cases)))  # remove duplicates

    case_serializer = TestCaseStudentSerializer(test_cases, many=True, context={'request': request})
    category_serializer = TestCategorySerializer(test_categories, many=True, context={'request': request})
    return Response({
        'id': assignment.id,
        'testCases': case_serializer.data,
        'testCategories': category_serializer.data
    })

  @action(detail=True, methods=["GET"])
  def beforeStudentUpload(self, request: Request, pk=None):
    """
    Get submission upload information

    return {
      "daysLate": 3,
      "pointsOff": 0,
      "lateDayCreditsAvailable": 2,
      "lateDayCreditsToUse": 2,
      "adjustedDaysLate": 0
    }
    """
    user = self.request.user
    assignment = Assignment.objects.get(id=pk)
    course = assignment.course

    if not isAuthenticated(user):
      return returnNotAuthorized()

    if not isStudent(user, course) or not assignment.allowStudentUpload:
      return returnForbidden()

    submission = Submission(assignment=assignment, dateUploaded=now())

    # FIXME: This will not check for partner submissions
    # We can't just have the POST body contain partner ids, for the same information
    # leak risks as allowing students to add partners without approval.
    handler = LateSubmissionHandler(submission, [user])

    if not handler.is_late():
      return Response({
          "daysLate": 0,
          "pointsOff": 0
      }, status=status.HTTP_200_OK)

    if course.lateDayCreditsAllowable == None:
      return Response({
          "daysLate": handler.real_days_late,
          "pointsOff": handler.get_points()
      }, status=status.HTTP_200_OK)
    else:
      return Response({
          "daysLate": handler.real_days_late,
          "pointsOff": handler.get_points(),
          "lateDayCreditsAvailable": handler.late_day_credits_available(),
          "lateDayCreditsToUse": handler.late_day_credits_to_use,
          "adjustedDaysLate": handler.calculated_days_late()
      }, status=status.HTTP_200_OK)

  @action(detail=True, methods=["GET"])
  def download(self, request: Request, pk=None):
    """
    download all files for an assignment files as a zip
    """
    user = request.user
    assignment = self.get_object()
    course = assignment.course

    if assignment.isVisible:
      if not isCourseMember(user, course):
        return returnForbidden()
    else:
      if not isCourseStaff(user, course):
        return returnForbidden()


    files = assignment.files.all()
    if len(files) == 0:
      return Response("No files to download", status=status.HTTP_204_NO_CONTENT)
    
    files_to_zip = []
    for f in files:
      files_to_zip.append(f)

    encoded = encoded_zip(files_to_zip)
    return Response({
        "zip": encoded,
        "filename": f"assignment{assignment.id}_files.zip"
    })
  
  # Upload assignment
  @action(detail=True, methods=["POST", "PATCH", "GET"])
  def studentUpload(self, request, pk=None):
    """
    Upload of submission to an assignment


    TODO: add file limits to 10mb
    """
    user = self.request.user
    assignment = Assignment.objects.get(id=pk)
    course = assignment.course

    if not isAuthenticated(user):
      return returnNotAuthorized()

    if not isStudent(user, course) or not assignment.allowStudentUpload:
      return returnForbidden()

    if request.method == "PATCH" or request.method == "POST":
      if 'files' not in request.data or len(request.data['files']) == 0:
        raise serializers.ValidationError("No files provided")


      # Began late submission check
      if assignment.uploadDueDate and now() > assignment.uploadDueDate:
        if not assignment.allowLateUploads:
          raise serializers.ValidationError("Late submissions are not allowed for this assignment.")
        
        # Calculate maxLateDate
        maxLateDate = assignment.uploadDueDate + timedelta(days=assignment.maxLateDays)
        if now() > maxLateDate:
          raise serializers.ValidationError("The maximum late submission period has passed for this assignment.")
        
      # Ended late submission check
      
      
      

      # Check to make sure the files are valid before we create the submission
      uploaded_filenames = set()
      MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB

      for f in request.data['files']:
        serializer = FileValidationSerializerWithoutSubmission(data=f)

        try:
          serializer.is_valid(raise_exception=True)
          
          # Check file size (10MB limit)
          # 'data' field is the string content, but for size we might want bytes.
          # Assuming 'data' is text or base64? The model says "should be utf-8 encoded text".
          # A strict 10MB limit on text length is a fair approximation for now.
          if len(f.get('data', '')) > MAX_FILE_SIZE:
             raise ValidationError(f"File '{f['name']}' exceeds the 10MB size limit.")

          uploaded_filenames.add(f['name'])

        except ValidationError as e:
          if isinstance(e.detail, dict):
            e.detail['file'] = f['name']
          else:
             # If it's a list or string, wrap it
             e = ValidationError({'file': f['name'], 'error': e.detail})
          raise e

      # Check for required files
      required_files = assignment.files.filter(required=True)
      missing_files = []
      for req_file in required_files:
        if req_file.name not in uploaded_filenames:
          missing_files.append(req_file.name)
      
      if missing_files:
        raise serializers.ValidationError(f"Missing required files: {', '.join(missing_files)}")



      otherSubs = Submission.objects.filter(assignment=pk, students__in=[user])
      if len(otherSubs) > 1:
        raise serializers.ValidationError("This student has multiple submissions for this assignment")

      
      if len(otherSubs) == 1:
        submission = otherSubs[0]
      else:
        submission = Submission.objects.create(assignment=assignment)
        submission.students.add(user)
        submission.save()
        
      # Don't allow submission if the submission is finalized, unless we are in LiveFeedbackMode
      if submission.isFinalized and not assignment.liveFeedbackMode:
        raise serializers.ValidationError("Cannot edit this submission, grading has started.")

      oldFiles = submission.files.all()
      print(oldFiles)
      if (request.method == "POST"):
        # Only if the request is a post do we replace all the submissions
        for f in oldFiles:
          print(f)
          f.delete()
          
          
      for f in request.data['files']:
        # Create new submission file
        SubmissionFile.objects.create(name=f['name'], data=f['data'], submission=submission, extension=f[
                                   'extension'], path=f['path'] if f['path'] else None)

      # Update submission date once files have been uploaded, triggers auto-execution celery task
      submission.dateUploaded = now()

      if assignment.liveFeedbackMode:
        submission.isFinalized = False

      submission.save()

      

      

      ###############################################################
      # [Begin] Late Logic
      ###############################################################

      handler = LateSubmissionHandler(submission)
      try:
        handler.handle()
      except Exception as e:
        logEvent("Late Submission Error",
                 message=f"Error handling late submission: {e} for submission by user {user.email}", level=logging.ERROR)


      ###############################################################
      # [End] Late Logic
      ###############################################################

      # Send upload receipt to each student
      if 'sendConfirmationEmail' in request.data and request.data['sendConfirmationEmail']:
        for student in submission.students.all():
          try:
            StudentUploadReceiptEmail(student).send_email(submission)
            # send_email_student_uploaded_submission(student.email, submission)
          except Exception as e:
            logEvent("API Error",
                     message=f"Error emailing student receipt: {e} for submission by user {user.email}", level=logging.ERROR)
      

      serializer = StudentSubmissionSerializer(submission, many=False, context={"request": request})
      return Response(serializer.data)

    # If a GET request, pass back the files for the submission
    else:
      otherSubs = Submission.objects.filter(assignment=pk, students__in=[user])
      if len(otherSubs) == 0:
        submission = None
        return Response({"id": -1, "files": []})
      else:
        submission = otherSubs[0]
        # Remove any autogenerated test files from being exposed
        filesToReturn = submission.files.filter(hiddenBeforePublish=False)
        toRet = {
            'id': submission.id, 'files': SubmissionFileStudentUploadSerializer(filesToReturn, many=True).data
        }
        return Response(toRet)

  @action(detail=True, methods=["GET"], pagination_class=LargeObjectsPagination)
  def submissionTests(self, request, pk=None):
    """
    Gets a paginated list of submission tests for an assignment.
    We use this for performance for large courses to fetch all submission tests.
    Fetching thousands of requests from the client can cause some to fail.
    Returns a list of {id: int, tests: SubmissionTest[]}
    """
    user = request.user
    assignment = self.get_object()
    course = assignment.course

    # Only allow course admins to access this endpoint
    if not isCourseAdmin(user, course):
      return returnForbidden()

    submissions = assignment.submissions.all().prefetch_related('tests')

    page = self.paginate_queryset(submissions)
    if page is not None:
      serializer = SubmissionWithTestsSerializer(page, many=True)
      return self.get_paginated_response(serializer.data)

    serializer = SubmissionWithTestsSerializer(submissions, many=True)
    return Response(serializer.data)


  @action(detail=True, methods=["GET"])
  def datasets(self, request, pk=None):
    """
    Return all datasets for this assignment
    
    GET /api/assignments/{id}/datasets/
    """
    from core.models import AssignmentDataSet
    from core.serializers.assignmentDataSet import AssignmentDataSetSerializer
    
    assignment = self.get_object()
    datasets = AssignmentDataSet.objects.filter(assignment=assignment).order_by('name')
    serializer = AssignmentDataSetSerializer(datasets, many=True, context={'request': request})
    return Response(serializer.data)

  @action(detail=True, methods=["POST"])
  def clone(self, request, pk=None):
    """
    Clone an assignment to a course
    """
    user = self.request.user
    assignment = self.get_object()
    course = assignment.course

    destination_course_id = request.data.get('course', course.id)
    destination_course = Course.objects.get(id=destination_course_id)

    if not isCourseAdmin(user, destination_course):
      return returnForbidden()

    if not isCourseAdmin(user, course):
      return returnForbidden()

    copied_assignment = copy_assignment(assignment, destination_course)

    if copied_assignment is None:
      return returnInvalid()

    # Return the newly created assignment data so frontend can navigate to it
    serializer = AssignmentSerializer(copied_assignment, context={'request': request})
    return Response(serializer.data)
