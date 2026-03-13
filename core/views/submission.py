# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import Submission, SubmissionTest, TestCase, TestCategory, File

from core.serializers.submission import AnonymousSubmissionSerializer, SubmissionSerializer, StudentSubmissionSerializer, StudentSubmissionWithoutGradeSerializer, StudentSubmissionFilesOnlySerializer
from core.serializers.submissionHistory import SubmissionHistorySerializer
from core.serializers.submissionTest import SubmissionTestSerializer

from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from core.serializers.actionResponses import (
  SubmissionCheckPermissionResponseSerializer,
  SubmissionTestResultsResponseSerializer,
  SubmissionPartnerLinkResponseSerializer,
)
from rest_framework import status

from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import SubmissionPermissions

from core.permissions.helpers import returnForbidden, returnNotFound, returnInvalid
from core.permissions.helpers import isStudent, isCourseStaff, isCourseAdmin, isStudentOfSub, isStaffOfSub, canViewUnanonymizedSubmissions, isSectionLeaderOfStudent, isSuperGrader

from django.contrib.auth.models import User
from rest_framework import serializers
from django.utils.timezone import now

from core.permissions.helpers import isAuthenticated

from autograder.run import filterExposedSubmissionTests
import json
from rest_framework import serializers

from core.permissions.tokens import submission_token_generator

from core.emails import StudentFeedbackNotificationEmail, StudentPartnersAddedEmail
from django.db.models import Q

def get_student_serializer_class(submission, files_only=False):
    """
    Get the appropriate serializer for a student viewing their submission.
    
    Args:
        submission: The submission object
        files_only: If True, return serializer with only files (no comments/grades)
    """
    if files_only:
        return StudentSubmissionFilesOnlySerializer
    
    # StudentSubmissionSerializer handles all cases:
    # - Masks grade when feedbackReleased is False
    # - Returns files without comments when feedbackReleased is False
    # - Preserves real isFinalized status so frontend can show submission correctly
    return StudentSubmissionSerializer



class SubmissionViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the submissions.

  create:
  Create a new submission.

  retrieve:
  Return the given submission.

  update:
  Update a submission.

  partial_update:
  Update a submission.

  delete:
  Delete a submission.
  """
  queryset = Submission.objects.all()
  serializer_class = SubmissionSerializer
  permission_classes = (IsAuthenticated, SubmissionPermissions)

  def get_serializer_class(self):
    # During schema generation, return default serializer
    if getattr(self, 'swagger_fake_view', False):
        return SubmissionSerializer
        
    if self.action in ['retrieve', 'update', 'partial_update']:
        user = self.request.user
        submission = self.get_object()
        assignment = submission.assignment
        course = submission.assignment.course

        # Check if files-only mode is requested
        files_only = self.request.query_params.get('filesOnly', 'false').lower() == 'true'

        # NOTE: we need to write this logic in descending order of privilege. For example, if a user
        # is both an admin and a student, we don't want to restrict that user's access to submissions
        # of which that user is a student before the associated assignment is released

        if isCourseAdmin(user, course):
            return SubmissionSerializer
        elif isCourseStaff(user, course):
          if isStudentOfSub(user, submission):
            return get_student_serializer_class(submission, files_only=files_only)
          elif (not assignment.anonymousGrading) or canViewUnanonymizedSubmissions(user, course):
            return SubmissionSerializer
          else:
            return AnonymousSubmissionSerializer
        else:
          # user is *only* a student
          return get_student_serializer_class(submission, files_only=files_only)

    else:
        return SubmissionSerializer


  @extend_schema(responses=SubmissionCheckPermissionResponseSerializer)
  @action(detail=True, methods=['get'])
  def checkPermission(self, request, pk=None):
    user = request.user
    try:
      submission = Submission.objects.get(id=pk)
    except Submission.DoesNotExist:
      return returnNotFound()

    if isStaffOfSub(user, submission):
      toRet = {
        'read': True,
        'write': True,
        'filesOnly': False,
      }
    elif isStudentOfSub(user, submission):
      # Students can ALWAYS view their submission (files)
      # But can only see full feedback (comments/grades) after feedbackReleased is True or liveFeedbackMode is on
      canReadFull = submission.assignment.feedbackReleased or submission.assignment.liveFeedbackMode
      toRet = {
        'read': True,  # Always allow read access to files
        'write': False,
        'filesOnly': not canReadFull,  # If feedback not released, restrict to files only
      }
    else:
      toRet = {
        'read': False,
        'write': False,
        'filesOnly': False,
      }

    return Response(toRet)


# Optional argument: student username
  @extend_schema(responses=SubmissionHistorySerializer(many=True))
  @action(detail=True, methods=['GET', 'PATCH'])
  def history(self, request, pk=None):
    user = request.user
    submission = Submission.objects.get(id=pk)
    course = submission.assignment.course

    student = self.request.query_params.get('student', None)

    isThisStudent = isStudent(user, course) and user.email == student
    submissionHistories = submission.histories.all().prefetch_related('student')

    # If you want all the submission's histories, you need to be an admin or supergrader of submission, and the request must be a get request
    studentParam = None
    if student is None:
      if request.method != "GET" or not isCourseAdmin(user, course) and not isStaffOfSub(user,submission):
        return returnForbidden()
    else:
    # Retrieve student
      try:
        studentParam = User.objects.filter(Q(username=student) | Q(email=student)).first()
        if studentParam is None:
          raise User.DoesNotExist
      except User.DoesNotExist:
        
        if isCourseAdmin(user, course):
          return returnNotFound(message="The user does not exist")
        else:
          return returnForbidden()
        

    # If you want to filter by the student, and want to post/patch/delete, you need to be the student
    # If you want to filter by the student, and get, then you need to be an admin, supergrader, or sectioNleader of student
    if student is not None:
      if request.method != "GET" and not isThisStudent:
        return returnForbidden()
      if not isThisStudent and not isCourseAdmin(user, course) and not isSuperGrader(user, course) and not isSectionLeaderOfStudent(user, course, studentParam):
        return returnForbidden()

    histories = submissionHistories.filter(student=studentParam) if studentParam is not None else submissionHistories
    if (request.method == "PATCH") and 'hasViewed' in request.data:
        newFields = {"student": studentParam.email, "hasViewed": request.data['hasViewed']}

        serializer = SubmissionHistorySerializer(histories[0], newFields, many=False, context={"request": request})
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
    else:
        serializer = SubmissionHistorySerializer(histories, many=True, context={"request": request})
        
    return Response(serializer.data)


################################# Regrade Functions ##########################################

  @extend_schema(responses=StudentSubmissionSerializer)
  @action(detail=True, methods=['PATCH'])
  def submitRegrade(self, request, pk=None):
    user = request.user
    submission = Submission.objects.get(id=pk)
    course = submission.assignment.course

    if not isStudentOfSub(user, submission):
      return returnForbidden()

    if not submission.assignment.allowRegradeRequests:
      raise serializers.ValidationError("Regrade requests are not enabled for this assignment.")

    if not submission.isFinalized:
      raise serializers.ValidationError("Your submission has not been graded yet. You can submit a regrade request after your submission has been graded.")

    if submission.questionResponder or submission.questionResponse:
      raise serializers.ValidationError("Your request is currently being reviewed by a grader. Changes cannot be made at this time.")

    if submission.assignment.regradeDeadline and now() > submission.assignment.regradeDeadline:
      raise serializers.ValidationError("The regrade request deadline for this assignment has passed.")

    # Current design decision is to not allow students to update their regrade request after submit
    if submission.questionText:
      raise serializers.ValidationError("You have already submitted a regrade request for this submission.")

    if 'questionText' not in request.data:
      raise serializers.ValidationError("questionText field is not provided.")

    if not request.data['questionText'].strip():
      raise serializers.ValidationError("questionText cannot be empty.")

    submission.questionIsOpen = True
    submission.questionText = request.data['questionText']
    if(request.data['questionIsRegrade']):
      submission.questionIsRegrade = True
    else:
      submission.questionIsRegrade = False

    submission.questionDate = now()
    submission.save()

    serializer = StudentSubmissionSerializer(submission, many=False, context={"request": request})

    return Response(serializer.data)

  @extend_schema(responses=StudentSubmissionSerializer)
  @action(detail=True, methods=['PATCH'])
  def deleteRegrade(self, request, pk=None):
    user = request.user
    submission = Submission.objects.get(id=pk)
    course = submission.assignment.course

    if not isStudentOfSub(user, submission):
      return returnForbidden()

    if not submission.assignment.allowRegradeRequests:
      raise serializers.ValidationError("Regrade requests are not enabled for this assignment.")

    if not submission.isFinalized:
      raise serializers.ValidationError("Your submission has not been graded yet.")

    if submission.questionResponder or submission.questionResponse:
      raise serializers.ValidationError("Your request is currently being reviewed by a grader. Changes cannot be made at this time.")

    submission.questionIsOpen = False
    submission.questionText = ''
    submission.questionDate = None
    submission.save()

    serializer = StudentSubmissionSerializer(submission, many=False, context={"request": request})

    return Response(serializer.data)


  #################################################################################
  #  DEPRACATED: Included here for backwards-compatibility
  #################################################################################

  @extend_schema(responses=SubmissionTestSerializer(many=True))
  @action(detail=True, methods=["GET"])
  def submissionTests(self, request, pk=None):
    #  Only accessed by students
    user = request.user
    submission = self.get_object()
    assignment = submission.assignment
    isStudentMode = self.request.query_params.get('isStudentMode', "False") == "True"

    # If admin and admin is not in studentmode
    if isStaffOfSub(user, submission) and not isStudentMode:
            tests = submission.tests.all()
    # If student of the submission
    elif isStudentOfSub(user, submission):
        if (assignment.isReleased and submission.isFinalized) or assignment.liveFeedbackMode:
            tests = submission.tests.all()
        else:
            maxFailedTests = assignment.environment and assignment.environment.maxExposedFailedTests
            tests = filterExposedSubmissionTests(list(submission.tests.all()), maxFailedTests)[0]
    else:
        returnForbidden()

    serializer = SubmissionTestSerializer(tests, many=True, context={"request": request})
    return Response(serializer.data)

  #################################################################################

  @extend_schema(responses=SubmissionTestResultsResponseSerializer)
  @action(detail=True, methods=["GET"])
  def testResults(self, request, pk=None):
    #  Only accessed by students
    user = request.user
    submission = Submission.objects.get(id=pk)
    assignment = submission.assignment
    isStudentMode = self.request.query_params.get('isStudentMode', "False") == "True"

    # contents of _tests.txt
    logCode = ''
    def retrieve_log_code(submission):
        try:
            logFile = File.objects.get(submission=submission, name="_tests.txt")
            return logFile.data
        except:
            return ''

    # If admin and admin is not in studentmode
    if isStaffOfSub(user, submission) and not isStudentMode:
            tests = submission.tests.all()
            logCode = retrieve_log_code(submission)
    # If student of the submission
    elif isStudentOfSub(user, submission):
        if (assignment.isReleased and submission.isFinalized) or assignment.liveFeedbackMode:
            tests = submission.tests.all()
            logCode = retrieve_log_code(submission)
        else:
            try:
                maxFailedTests = assignment.environment and assignment.environment.maxExposedFailedTests
            except:
                maxFailedTests = None

            tests = filterExposedSubmissionTests(list(submission.tests.all()), maxFailedTests)[0]

            try:
                logCode = retrieve_log_code(submission)
            except:
                logCode = ''

    else:
        returnForbidden()

    submissionTests = SubmissionTestSerializer(tests, many=True, context={"request": request}).data

    return Response({'submissionTests': submissionTests, 'logs': logCode})

  #################################################################################

  @extend_schema(responses=SubmissionPartnerLinkResponseSerializer)
  @action(detail=True, methods=["GET"])
  def generatePartnerLink(self, request, pk=None):
    user = request.user
    submission = Submission.objects.get(id=pk)
    assignment = submission.assignment

    if not assignment.allowStudentUploadWithPartners:
        return returnForbidden()

    if not isStudentOfSub(user, submission):
        return returnForbidden()

    if submission.isFinalized:
        return returnForbidden()

    token = submission_token_generator.make_token(submission)

    return Response({
      'id': submission.id,
      'token': token,
    })

  @extend_schema(
    responses=OpenApiTypes.STR,
    parameters=[
      OpenApiParameter(
        name="token",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=True,
      ),
    ],
  )
  @action(detail=True, methods=["GET"])
  def validatePartnerLink(self, request, pk=None):
    user = request.user
    submission = Submission.objects.get(id=pk)
    assignment = submission.assignment
    course = submission.assignment.course
    token = request.query_params.get('token', None)

    if not assignment.allowStudentUploadWithPartners:
        return returnInvalid()

    if not token:
        return returnInvalid()

    if not isStudent(user, course):
        return returnInvalid()

    current_submission = Submission.objects.filter(assignment=submission.assignment, students__in=[user])

    if len(current_submission) > 0:
        return returnInvalid()

    is_valid = submission_token_generator.check_token(submission, token)
    if is_valid:
        submission.students.add(user)

        for student in submission.students.all():         
            StudentPartnersAddedEmail(student).send_email(
                new_partner_email=user.email,
                submission=submission,
            )
            # send_email_updated_partners(student.email, user.email, ", ".join(list(submission.students.all().values_list('email', flat=True))), submission.assignment, course)

        return Response("ok", status.HTTP_200_OK)
    else:
        return returnInvalid()

  @extend_schema(
    responses=StudentSubmissionSerializer,
    parameters=[
      OpenApiParameter(
        name="token",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=True,
      ),
    ],
  )
  @action(detail=True, methods=["GET"])
  def validatePartnerLinkAndReturn(self, request, pk=None):
    user = request.user
    submission = Submission.objects.get(id=pk)
    assignment = submission.assignment
    course = submission.assignment.course
    token = request.query_params.get('token', None)

    if not assignment.allowStudentUploadWithPartners:
        return returnInvalid()

    if not token:
        return returnInvalid()

    if not isStudent(user, course):
        return returnInvalid()

    current_submission = Submission.objects.filter(assignment=submission.assignment, students__in=[user])

    if len(current_submission) > 0:
        return returnInvalid()

    is_valid = submission_token_generator.check_token(submission, token)
    if is_valid:
        serializer = StudentSubmissionSerializer(submission, many=False, context={"request": request})
        return Response(serializer.data)
    else:
        return returnInvalid()

  @extend_schema(responses=OpenApiTypes.STR)
  @action(detail=True, methods=["GET"])
  def removePartner(self, request, pk=None):
    user = request.user
    submission = Submission.objects.get(id=pk)

    if not isStudentOfSub(user, submission):
        return returnForbidden()

    submission.students.remove(user)

    return Response('ok')

  @extend_schema(responses=OpenApiTypes.STR)
  @action(detail=True, methods=["POST"])
  def notifyStudents(self, request, pk=None):
    user = request.user
    submission = Submission.objects.get(id=pk)

    if not isStaffOfSub(user, submission):
        return returnForbidden()

    if not submission.assignment.isReleased:
        return Response('Assignment must be released', status.HTTP_406_NOT_ACCEPTABLE)

    if not submission.isFinalized:
        return Response('Submission must be finalized', status.HTTP_406_NOT_ACCEPTABLE)

    # QUESTION: We could make the setting a requirement. Or we could make this globally accessible for staff.
    # if not submission.assignment.course.enableStudentFeedbackNotifications:
    #     return Response('Course EnableStudentFeedbackNotifications must be turned on', status.HTTP_406_NOT_ACCEPTABLE)

    view_submission_url = 'https://compedu.stanford.edu/codeinplace/v1/#/submissions' if submission.assignment.course.id == 925 else 'https://codepost.io/code/{}'.format(submission.id)

    

    for student in submission.students.all():
        StudentFeedbackNotificationEmail(student).send_email(submission)

    return Response('Notifications sent!', status.HTTP_200_OK)
