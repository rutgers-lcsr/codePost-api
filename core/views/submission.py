# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import Submission, SubmissionTest, TestCase, TestCategory, File

from core.serializers.submission import AnonymousSubmissionSerializer, SubmissionSerializer, StudentSubmissionSerializer, StudentSubmissionWithoutGradeSerializer, StudentSubmissionFilesOnlySerializer
from core.serializers.submissionHistory import SubmissionHistorySerializer
from core.serializers.submissionTest import SubmissionTestSerializer

from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers, status

from core.serializers.actionResponses import (
  SubmissionCheckPermissionResponseSerializer,
  SubmissionTestResultsResponseSerializer,
  SubmissionPartnerLinkResponseSerializer,
)
from core.serializers.suggested_comment import SuggestedCommentSerializer
from core.serializers.submission_summary import SubmissionSummarySerializer

from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import SubmissionPermissions

from core.permissions.helpers import returnForbidden, returnNotFound, returnInvalid
from core.permissions.helpers import isStudent, isCourseStaff, isCourseAdmin, isStudentOfSub, isStaffOfSub, canViewUnanonymizedSubmissions, isSectionLeaderOfStudent, isSuperGrader

from core.models import User
from rest_framework import serializers
from django.utils.timezone import now

from core.permissions.helpers import isAuthenticated

from autograder.run import filterExposedSubmissionTests
import json
from rest_framework import serializers

from core.permissions.tokens import submission_token_generator

from core.emails import StudentFeedbackNotificationEmail, StudentPartnersAddedEmail
from django.db.models import Q
from core.services.audit import record_audit_event

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

  def perform_create(self, serializer):
    submission = serializer.save()
    course = submission.assignment.course
    students = submission.students.all()
    user = students.first() if students.exists() else self.request.user
    record_audit_event(
        course=course,
        event_type='submission_attempt',
        user=user,
        assignment=submission.assignment,
        submission=submission,
    )

  def create(self, request, *args, **kwargs):
    try:
        return super().create(request, *args, **kwargs)
    except Exception as exc:
        # Log the failed submission attempt if we can determine the assignment
        assignment_id = request.data.get('assignment')
        if assignment_id:
            try:
                from core.models import Assignment
                assignment = Assignment.objects.select_related('course').get(id=assignment_id)
                record_audit_event(
                    course=assignment.course,
                    event_type='submission_failed',
                    user=request.user,
                    assignment=assignment,
                    meta={'error': str(exc)},
                )
            except Exception:
                pass
        raise

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
      # Record audit event for student viewing their submission
      course = submission.assignment.course
      if canReadFull:
          record_audit_event(
              course=course,
              event_type='feedback_view',
              user=user,
              assignment=submission.assignment,
              submission=submission,
          )
      else:
          record_audit_event(
              course=course,
              event_type='file_view',
              user=user,
              assignment=submission.assignment,
              submission=submission,
          )
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
        newFields = {"student": studentParam.email, "hasViewed": request.data['hasViewed']}  # type: ignore[union-attr]  # studentParam checked above

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

    record_audit_event(
        course=course,
        event_type='regrade_request',
        user=user,
        assignment=submission.assignment,
        submission=submission,
        meta={'questionText': request.data['questionText'], 'isRegrade': bool(request.data.get('questionIsRegrade'))},
    )

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

    record_audit_event(
        course=course,
        event_type='regrade_deleted',
        user=user,
        assignment=submission.assignment,
        submission=submission,
    )

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

  @extend_schema(
      responses=SuggestedCommentSerializer(many=True),
      description="List all pending AI-suggested comments for this submission. Staff only.",
  )
  @action(detail=True, methods=["GET"])
  def suggestedComments(self, request, pk=None):
    """Return pending suggested comments for this submission."""
    from core.models import SuggestedComment
    from core.serializers.suggested_comment import SuggestedCommentSerializer

    submission = self.get_object()
    user = request.user

    if not isStaffOfSub(user, submission):
        return returnForbidden()

    suggestions = SuggestedComment.objects.filter(
        submission=submission, status='pending'
    ).select_related('file', 'rubricComment')

    return Response(SuggestedCommentSerializer(suggestions, many=True).data)

  @extend_schema(
      responses=SubmissionSummarySerializer,
      description="Get the AI-generated summary for this submission. Staff only.",
  )
  @action(detail=True, methods=["GET"])
  def summary(self, request, pk=None):
    """Return the AI-generated summary for this submission."""
    from core.models import SubmissionSummary
    from core.serializers.submission_summary import SubmissionSummarySerializer

    submission = self.get_object()
    user = request.user

    if not isStaffOfSub(user, submission):
        return returnForbidden()

    try:
        summary_obj = SubmissionSummary.objects.get(submission=submission)
    except SubmissionSummary.DoesNotExist:
        return returnNotFound()

    return Response(SubmissionSummarySerializer(summary_obj).data)

  @extend_schema(
      responses={202: inline_serializer('GenerateAIAssistanceResponse', fields={
          'status': serializers.CharField(),
          'submissionId': serializers.IntegerField(),
      })},
      description="Manually trigger or regenerate AI summary and suggested comments. Staff only.",
  )
  @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated])
  def generateAIAssistance(self, request, pk=None):
    """Trigger AI grading assistance (summary + suggested comments) for this submission."""
    submission = Submission.objects.get(id=pk)
    user = request.user

    if not isStaffOfSub(user, submission):
        return returnForbidden()

    from core.tasks import generate_ai_grading_assistance
    generate_ai_grading_assistance.delay(submission.id)

    return Response({'status': 'queued', 'submissionId': submission.id}, status.HTTP_202_ACCEPTED)

  @extend_schema(
      request=inline_serializer('GenerateFileSuggestionsRequest', fields={
          'fileId': serializers.IntegerField(help_text="ID of the submission file to generate suggestions for."),
      }),
      responses=SuggestedCommentSerializer(many=True),
      description="Generate AI-suggested comments for a specific file in this submission. Runs synchronously. Staff only.",
  )
  @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated])
  def generateFileSuggestions(self, request, pk=None):
    """Generate AI suggestions for a single file within this submission."""
    import json
    from asgiref.sync import async_to_sync
    from core.models import SuggestedComment, SubmissionFile
    from core.serializers.suggested_comment import SuggestedCommentSerializer as SCSer
    from core.services.ai_service import AIService

    submission = self.get_object()
    user = request.user

    if not isStaffOfSub(user, submission):
        return returnForbidden()

    file_id = request.data.get('fileId')
    if not file_id:
        return Response({'error': 'fileId is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        file_obj = SubmissionFile.objects.get(id=file_id, submission=submission)
    except SubmissionFile.DoesNotExist:
        return returnNotFound()

    course = submission.assignment.course
    service = AIService(course, submission.assignment)

    if not service.is_configured:
        return Response({'error': 'AI is not configured for this course.'}, status=status.HTTP_400_BAD_REQUEST)

    results = async_to_sync(service.generate_file_suggestions)(submission, file_obj)

    # Clear existing pending suggestions for this file to prevent duplicates
    SuggestedComment.objects.filter(
        submission=submission, file=file_obj, status='pending'
    ).delete()

    created = []
    for result in results:
        if result.success and result.text:
            try:
                suggestions = json.loads(result.text)
            except (json.JSONDecodeError, TypeError):
                return Response(
                    {'error': 'AI returned malformed output. Please try again.'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            is_notebook = file_obj.name.endswith('.ipynb')
            for s in suggestions:
                if s.get('file_id') != file_obj.id:
                    continue
                # For notebooks, convert 1-based cell numbers to 0-based indices
                start_line = s.get('start_line', 0)
                end_line = s.get('end_line', 0)
                if is_notebook:
                    start_line = max(0, start_line - 1)
                    end_line = max(0, end_line - 1)
                created.append(SuggestedComment.objects.create(
                    submission=submission,
                    file=file_obj,
                    text=s.get('text', ''),
                    startLine=start_line,
                    endLine=end_line,
                    startChar=s.get('start_char', 0),
                    endChar=s.get('end_char', 0),
                    rubricComment_id=s.get('rubric_comment_id'),
                    pointDelta=s.get('point_delta'),
                    generationMetadata={
                        'provider': service.provider,
                        'model': service.model,
                        'input_tokens': result.input_tokens,
                        'output_tokens': result.output_tokens,
                    },
                ))
            service.record_usage(result, user, request_type='file_suggestions')
        elif not result.success:
            return Response({'error': result.error or 'AI generation failed.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(SCSer(created, many=True).data, status=status.HTTP_201_CREATED)

  @extend_schema(
      request=None,
      responses=SubmissionSummarySerializer,
      description="Generate or regenerate the AI summary for this submission. Runs synchronously. Staff only.",
  )
  @action(detail=True, methods=["POST"], permission_classes=[IsAuthenticated])
  def generateSummary(self, request, pk=None):
    """Generate or regenerate the AI summary for this submission on demand."""
    from asgiref.sync import async_to_sync
    from core.models import SubmissionSummary
    from core.serializers.submission_summary import SubmissionSummarySerializer as SSSer
    from core.services.ai_service import AIService

    submission = self.get_object()
    user = request.user

    if not isStaffOfSub(user, submission):
        return returnForbidden()

    course = submission.assignment.course
    service = AIService(course, submission.assignment)

    if not service.is_configured:
        return Response({'error': 'AI is not configured for this course.'}, status=status.HTTP_400_BAD_REQUEST)

    if service.is_globally_disabled:
        return Response({'error': 'AI is disabled for this course.'}, status=status.HTTP_400_BAD_REQUEST)

    result = async_to_sync(service.generate_submission_summary)(submission)

    if not result.success:
        return Response({'error': result.error or 'AI generation failed.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    summary_obj, _ = SubmissionSummary.objects.update_or_create(
        submission=submission,
        defaults={
            'text': result.text,
            'generationMetadata': {
                'provider': service.provider,
                'model': service.model,
                'input_tokens': result.input_tokens,
                'output_tokens': result.output_tokens,
            },
        },
    )

    service.record_usage(result, user, request_type='submission_summary')

    return Response(SSSer(summary_obj).data, status=status.HTTP_201_CREATED)
