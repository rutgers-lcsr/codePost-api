from core.models import Course, Assignment, RubricCategory, RubricComment, Submission, File, TestCase, TestCategory
from rest_framework import serializers
from core.serializers.assignment import AssignmentSerializer, AssignmentSerializerWithStatistics, AssignmentStudentSerializer, AssignmentSerializerWithStatisticsAndSummary
from core.serializers.submission import AnonymousSubmissionSerializer, SubmissionSerializer, StudentSubmissionSerializer, StudentSubmissionWithoutGradeSerializer, SubmissionStatusSerializer, SubmissionSerializerWithoutFiles, SubmissionWithTestsSerializer
from core.serializers.rubricCategory import RubricCategorySerializer, RubricCategoryStudentSerializer
from core.serializers.rubricComment import RubricCommentSerializer
from core.serializers.submissionHistory import SubmissionHistorySerializer
from core.serializers.comment import CommentSerializer

from core.serializers.testCase import TestCaseStudentSerializer
from core.serializers.testCategory import TestCategorySerializer
from core.serializers.file import FileValidationSerializerWithoutSubmission, FileStudentUploadSerializer


from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from core.models import Section, SubmissionHistory, Comment
from mooc.models import Credit

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

from core.utils import get_mooc_courses, copy_assignment
from core.handlers.late_submission_handler import LateSubmissionHandler
from core.handlers.submission_version_handler import SubmissionVersionHandler

from util.slack import Slack
from autograder.testUtils.logging import standardLog
import datetime
import pytz

import io
import zipfile
import base64
from core.emails import send_email_sendgrid, get_email_template_id, get_email_params


def encoded_zip(files):
  """
  Create zip from files in memory
  """
  zip_buffer = io.BytesIO()

  with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
    for file in files:
      zip_file.writestr(file.name, file.code)

  return base64.b64encode(zip_buffer.getvalue()).decode()


def send_email_student_uploaded_submission(to_email, submission):

  # Only zip the most recent submission
  files = SubmissionVersionHandler(submission).current_files()

  tz = pytz.timezone(submission.assignment.course.timezone)
  dateUploaded = submission.dateUploaded.astimezone(tz)

  dateUploadedHumanize = dateUploaded.strftime("%A, %m-%d-%Y %H:%M:%S")
  dateUploadedTimestamp = dateUploaded.strftime("%Y%m%d_%H%M")

  zip_name = "{}_{}_{}.zip".format(to_email, submission.id, dateUploadedTimestamp)

  attachments = [
      {
          "content": encoded_zip(files),
          "filename": zip_name,
          "type": "application/zip"
      }
  ]

  context = {
      'assignmentName': submission.assignment.name,
      'courseName': "{} | {}".format(submission.assignment.course.name, submission.assignment.course.period),
      'students': ", ".join(list(submission.students.all().values_list('email', flat=True))),
      'dateUploadedHumanize': dateUploadedHumanize,
      'dateUploadedTimestamp': dateUploadedTimestamp
  }

  send_email_sendgrid(from_email="team@codepost.io", to_email=to_email, params=get_email_params(
      'STUDENT_UPLOAD_RECEIPT', context), templateID=get_email_template_id('STUDENT_UPLOAD_RECEIPT'), attachments=attachments)

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
  queryset = Assignment.objects.all()
  permission_classes = (IsAuthenticated, AssignmentPermissions)
  serializer_class = AssignmentSerializer

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
          return AssignmentSerializer
        else:
          return AssignmentSerializerWithStatistics
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

    toRet = {
        'id': assignment.id,
        'unclaimed': assignment.submissions.filter(grader=None).count(),
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
    if len(submissions) > 0:
      submission = submissions[0]
      # Assign submission to grader
      # Doing this in this call is important, since it prevents two users from drawing the
      # save unassigned submission and subsequently trying to claim it
      submission.grader = user
      submission.save()

      serializerClass = SubmissionSerializer
      if assignment.anonymousGrading and not canViewUnanonymizedSubmissions(user, course):
        serializerClass = AnonymousSubmissionSerializer

      serializer = serializerClass(submission, context={'request': request})
      return Response(serializer.data)
    else:
      return Response(status=status.HTTP_204_NO_CONTENT)

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
        studentParam = User.objects.get(username=student)
      except User.DoesNotExist:
        if isCourseAdmin(user, course):
          return returnNotFound(message="The user does not exist")
        else:
          return returnForbidden()

    # Retrieve grader
    graderParam = None
    if grader is not None:
      try:
        graderParam = User.objects.get(username=grader)
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

      # If assignment is in live feedback mode, don't check for finalized or assingment release
      if assignment.liveFeedbackMode:
        if assignment.hideGrades:
          serializer = StudentSubmissionWithoutGradeSerializer(filteredSubs, many=True, context={'request': request})
        else:
          serializer = StudentSubmissionSerializer(filteredSubs, many=True, context={'request': request})

      else:
        if (not assignment.isReleased) or (not subCandidate.isFinalized):
          serializer = SubmissionStatusSerializer(filteredSubs, many=True, context={'request': request})
        elif assignment.hideGrades:
          serializer = StudentSubmissionWithoutGradeSerializer(filteredSubs, many=True, context={'request': request})
        else:
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
  def submissionHistories(self, request, pk=None):
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
  def beforeStudentUpload(self, request, pk=None):
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

  # Upload assignment
  @action(detail=True, methods=["POST", "PATCH", "GET"])
  def studentUpload(self, request, pk=None):
    """
    Upload of submission to an assignment
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

      if assignment.uploadDueDate and now() > assignment.uploadDueDate and (not assignment.allowLateUploads):
        raise serializers.ValidationError("Due date has passed")

      # Check to make sure the files are valid before we create the submission
      for f in request.data['files']:
        serializer = FileValidationSerializerWithoutSubmission(data=f)

        try:
          serializer.is_valid(raise_exception=True)
        except Exception as e:
          e.detail['file'] = f['name']
          raise ValidationError(e)


      otherSubs = Submission.objects.filter(assignment=pk, students__in=[user])
      if len(otherSubs) > 1:
        raise serializers.ValidationError("This student has multiple submissions for this assignment")

      ###############################################################
      # [Begin] MOOC Handling
      ###############################################################
      if course.id in get_mooc_courses():

        credit = Credit.objects.filter(user=user, assignment=assignment)
        if not credit:
          raise serializers.ValidationError("Missing valid Credit for submission")
        else:
          credit = credit.first()
      ###############################################################
      # [End] MOOC Handling
      ###############################################################

      if len(otherSubs) == 1:
        submission = otherSubs[0]

        # Don't allow submission if the submission is finalized, unless we are in LiveFeedbackMode
        if submission.isFinalized and not assignment.liveFeedbackMode:
          raise serializers.ValidationError("Cannot edit this submission, grading has started.")

        oldFiles = submission.files.all()
        if (request.method == "POST"):
          # Only if the request is a post do we replace all the submissions
          for f in oldFiles:
            f.delete()
        submission.dateUploaded = now()

        if assignment.liveFeedbackMode:
          submission.isFinalized = False

        submission.save()

      else:
        submission = Submission.objects.create(assignment=assignment)
        submission.students.add(user)
        submission.save()

      ###############################################################
      # [Begin] MOOC Handling
      ###############################################################
      if course.id in get_mooc_courses() and credit:
        credit.submission = submission
        credit.save()

        try:
          blocks = [
              {
                  "type": "section",
                  "text": {
                      "type": "mrkdwn",
                      "text": "*Assignment Submitted*\n:👉 [dashboard](https://dasbhoard.codepost.io)"
                  }
              },
              {
                  "type": "section",
                  "fields": [
                      {
                          "type": "mrkdwn",
                          "text": "*Course:*\n{}".format(str(course))
                      },
                      {
                          "type": "mrkdwn",
                          "text": "*Assignment:*\n{}".format(str(assignment))
                      },
                      {
                          "type": "mrkdwn",
                          "text": "*User:*\n{}".format(user.id)
                      },
                      {
                          "type": "mrkdwn",
                          "text": "*When:*\n{}".format(datetime.datetime.now(pytz.timezone('US/Eastern')).strftime("%Y-%m-%d %H:%M:%S"))
                      },
                      {
                          "type": "mrkdwn",
                          "text": "*Submission:*\n[{}](https://codepost.io/code/{})".format(submission.id, submission.id)
                      },
                      {
                          "type": "mrkdwn",
                          "text": "*Approve:*\n[{}](https://api.codepost.io/admin/mooc/review/{})".format(credit.id, credit.id)
                      }
                  ]
              }]
          slack_client = Slack()
          slack_client.send_message('[FaaS] New Submission', blocks=blocks, channel="coursera_algorithms-1")
        except:
          slack_client = Slack()
          slack_client.send_message('Something went wrong sending FaaS notification', channel="coursera_algorithms-1")
      ###############################################################
      # [End] MOOC Handling
      ###############################################################

      for f in request.data['files']:
        file = File.objects.create(name=f['name'], code=f['code'], submission=submission, extension=f[
                                   'extension'], path=f['path'] if f['path'] else None)

      ###############################################################
      # [Begin] Late Logic
      ###############################################################

      handler = LateSubmissionHandler(submission)
      try:
        handler.handle()
      except Exception as e:
        sc = Slack()
        sc.send_message("Error handling late submission: {}".format(
            e), channel="#user_notifications", logInDebug=True, debugChannel="richard-test")

      ###############################################################
      # [End] Late Logic
      ###############################################################

      # Send upload receipt to each student
      if 'sendConfirmationEmail' in request.data and request.data['sendConfirmationEmail']:
        for student in submission.students.all():
          try:
            send_email_student_uploaded_submission(student.email, submission)
          except Exception as e:
            sc = Slack()
            sc.send_message("Error emailing student receipt: {}".format(
                e), channel="#user_notifications", logInDebug=True, debugChannel="richard-test")

      serializer = SubmissionStatusSerializer(submission, many=False, context={"request": request})
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
            'id': submission.id, 'files': FileStudentUploadSerializer(filesToReturn, many=True).data
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

    return Response("Success!")
