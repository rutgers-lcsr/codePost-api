# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils import timezone

from core.models import Quiz
from core.serializers.quiz import QuizSerializer, QuizQuestionSerializer
from core.serializers.generatedQuiz import (
    GeneratedQuestionSetListSerializer, GeneratedQuestionSetSerializer,
)
from core.serializers.studentQuiz import (
    StaffQuizAttemptSerializer, serialize_score, staff_reveal_context,
)
from core.services import quiz_grading
from core.services.audit import record_audit_event
from core.views.template import ListProtectedViewSet
from core.permissions.helpers import isCourseAdmin, isCourseStaff, isStudent
from core.permissions.permissions import (
    QuizPermissions, canGradeQuiz, canReviewGeneratedQuestions,
)


# ---- Action guards: each returns an error Response, or None when allowed. ---- #

def _forbidden(detail):
  return Response({'detail': detail}, status=status.HTTP_403_FORBIDDEN)


def _review_guard(user, quiz):
  """Generated-question review actions: admins always, staff per the quiz flag."""
  if canReviewGeneratedQuestions(user, quiz):
    return None
  return _forbidden('You do not have permission to review generated questions on this quiz.')


def _grading_guard(user, quiz, detail):
  if canGradeQuiz(user, quiz.course):
    return None
  return _forbidden(detail)


def _admin_guard(user, quiz, detail):
  if user.is_superuser or isCourseAdmin(user, quiz.course):
    return None
  return _forbidden(detail)


def _generation_ready_guard(quiz):
  """AI-generation actions need sections, an attached assignment, and the feature on."""
  from core.services.ai_service import AIService
  if not quiz.generatedSections.exists():
    return Response({'error': 'This quiz has no AI-generated sections.'},
                    status=status.HTTP_400_BAD_REQUEST)
  if quiz.assignment_id is None:
    return Response({'error': 'This quiz is not attached to an assignment.'},
                    status=status.HTTP_400_BAD_REQUEST)
  if not AIService(quiz.course, quiz.assignment).is_feature_enabled('personalized_quiz_generation'):
    return Response({'error': "AI quiz question generation is not enabled for this course. "
                              "Enable the 'AI-Generated Quiz Questions' AI feature in the "
                              "course's AI settings first."},
                    status=status.HTTP_400_BAD_REQUEST)
  return None


class QuizViewSet(ListProtectedViewSet):
  """Quizzes: authoring containers of questions, optionally attached to an assignment.

  Attach a quiz to an existing assignment by PATCHing its ``assignment`` field.
  """
  queryset = Quiz.objects.select_related('course', 'assignment', 'createdBy').prefetch_related(
      'quizQuestions__question').all()
  serializer_class = QuizSerializer
  permission_classes = (IsAuthenticated, QuizPermissions)

  def perform_create(self, serializer):
    quiz = serializer.save()
    record_audit_event(course=quiz.course, event_type='quiz_created', user=self.request.user,
                       quiz=quiz, assignment=quiz.assignment,
                       meta={'title': quiz.title, 'isPublished': quiz.isPublished})

  def perform_update(self, serializer):
    was_published = serializer.instance.isPublished
    quiz = serializer.save()
    if quiz.isPublished != was_published:
      event_type = 'quiz_published' if quiz.isPublished else 'quiz_unpublished'
    else:
      event_type = 'quiz_updated'
    record_audit_event(course=quiz.course, event_type=event_type, user=self.request.user,
                       quiz=quiz, assignment=quiz.assignment, meta={'title': quiz.title})

  def perform_destroy(self, instance):
    course, assignment, title, quiz_id = (
        instance.course, instance.assignment, instance.title, instance.id)
    instance.delete()
    record_audit_event(course=course, event_type='quiz_deleted', user=self.request.user,
                       assignment=assignment, meta={'title': title, 'quizId': quiz_id})

  @extend_schema(responses=QuizQuestionSerializer(many=True))
  @action(detail=True, methods=['GET'])
  def questions(self, request, pk=None):
    """List this quiz's question memberships, in order."""
    quiz = self.get_object()
    memberships = quiz.quizQuestions.select_related('question').all()
    return Response(QuizQuestionSerializer(memberships, many=True, context={'request': request}).data)

  @extend_schema(
      parameters=[OpenApiParameter(name='needsGrading', type=bool, location=OpenApiParameter.QUERY,
                                   required=False, description='Only attempts awaiting manual grading.')],
      responses=StaffQuizAttemptSerializer(many=True),
  )
  @action(detail=True, methods=['GET'])
  def attempts(self, request, pk=None):
    """Submitted attempts on this quiz, for grading — quiz graders and course admins only."""
    quiz = self.get_object()
    denied = _grading_guard(request.user, quiz,
                            'Only quiz graders and course admins can view attempts for grading.')
    if denied:
      return denied
    attempts = quiz.attempts.filter(status='submitted').select_related(
        'student', 'quiz').prefetch_related('responses').order_by('student__email', 'attemptNumber')
    if request.query_params.get('needsGrading') in ('true', 'True', '1'):
      attempts = attempts.filter(needsManualGrading=True)
    return Response(StaffQuizAttemptSerializer(
        attempts, many=True, context=staff_reveal_context(request)).data)

  @extend_schema(
      responses=inline_serializer('QuizResultRow', {
          'student': serializers.EmailField(),
          'attemptsUsed': serializers.IntegerField(),
          'score': serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True),
          'maxScore': serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True),
          'passed': serializers.BooleanField(allow_null=True),
          'needsGrading': serializers.BooleanField(),
          'lastSubmittedAt': serializers.DateTimeField(allow_null=True),
      }, many=True),
  )
  @action(detail=True, methods=['GET'])
  def results(self, request, pk=None):
    """Per-student official results (per this quiz's scoringPolicy) — quiz graders and
    course admins only. Score is null until the student has a fully graded attempt."""
    quiz = self.get_object()
    denied = _grading_guard(request.user, quiz,
                            'Only quiz graders and course admins can view quiz results.')
    if denied:
      return denied
    by_student = {}
    for attempt in quiz.attempts.filter(status='submitted').select_related('student').order_by(
        'student__email', 'attemptNumber'):
      by_student.setdefault(attempt.student, []).append(attempt)
    rows = []
    for student, attempts in by_student.items():
      # The attempts are already in hand — no per-student re-query.
      official = quiz_grading.official_score(quiz, student, attempts=attempts)
      rows.append({
          'student': student.email,
          'attemptsUsed': len(attempts),
          'score': serialize_score(official[0]) if official else None,
          'maxScore': serialize_score(official[1]) if official else None,
          'passed': quiz_grading.official_passed(quiz, student, official=official) if official else None,
          'needsGrading': any(a.needsManualGrading for a in attempts),
          'lastSubmittedAt': max((a.submittedAt for a in attempts if a.submittedAt), default=None),
      })
    return Response(rows)

  @extend_schema(
      request=None,
      responses=inline_serializer('ResetQuizAttemptsResponse', {'deleted': serializers.IntegerField()}),
      description="Delete ALL student attempts for this quiz (course admins only). Use after a "
                  "substantive edit so students retake from scratch. Irreversible; responses cascade.",
  )
  @action(detail=True, methods=['POST'])
  def resetAttempts(self, request, pk=None):
    quiz = self.get_object()
    denied = _admin_guard(request.user, quiz, 'Only course admins can reset attempts.')
    if denied:
      return denied
    deleted, _ = quiz.attempts.all().delete()
    record_audit_event(course=quiz.course, event_type='quiz_attempts_reset', user=request.user,
                       quiz=quiz, assignment=quiz.assignment, meta={'title': quiz.title})
    return Response({'deleted': deleted}, status=status.HTTP_200_OK)

  @extend_schema(responses=GeneratedQuestionSetListSerializer(many=True))
  @action(detail=True, methods=['GET'])
  def generatedSets(self, request, pk=None):
    """Per-student generated question sets on this quiz, for review. Course admins
    always; other staff only when gradersCanReviewGenerated is on."""
    quiz = self.get_object()
    denied = _review_guard(request.user, quiz)
    if denied:
      return denied
    sets = quiz.generatedSets.select_related('student', 'submission').prefetch_related(
        'questions').order_by('student__email')
    return Response(GeneratedQuestionSetListSerializer(
        sets, many=True, context={'request': request}).data)

  @extend_schema(
      request=None,
      responses=inline_serializer('PublishAllGeneratedResponse', {
          'approved': serializers.IntegerField(), 'skipped': serializers.IntegerField()}),
      description="Approve every generated set awaiting review on this quiz in one step "
                  "(course admins only). Sets with no questions are skipped.",
  )
  @action(detail=True, methods=['POST'])
  def publishAllGenerated(self, request, pk=None):
    quiz = self.get_object()
    denied = _admin_guard(request.user, quiz, 'Only course admins can publish all generated sets.')
    if denied:
      return denied
    approved = skipped = 0
    now = timezone.now()
    for gen_set in quiz.generatedSets.filter(status='ready').prefetch_related('questions'):
      if not gen_set.questions.exists():
        skipped += 1
        continue
      gen_set.status = 'approved'
      gen_set.approvedBy = request.user
      gen_set.approvedAt = now
      gen_set.save(update_fields=['status', 'approvedBy', 'approvedAt', 'modified'])
      approved += 1
    record_audit_event(course=quiz.course, event_type='quiz_generated_sets_published',
                       user=request.user, quiz=quiz, assignment=quiz.assignment,
                       meta={'title': quiz.title, 'approved': approved, 'skipped': skipped})
    return Response({'approved': approved, 'skipped': skipped}, status=status.HTTP_200_OK)

  @extend_schema(
      request=inline_serializer('GenerateForStudentRequest', {
          'student': serializers.EmailField(),
          'force': serializers.BooleanField(required=False, default=False),
      }),
      responses=GeneratedQuestionSetSerializer,
      description="Generate (or regenerate) this quiz's AI questions for one student from "
                  "their latest submission — useful for testing a prompt or backfilling after "
                  "enabling the feature. An approved set is only regenerated with force=true "
                  "(it becomes un-published until re-approved).",
  )
  @action(detail=True, methods=['POST'])
  def generateForStudent(self, request, pk=None):
    from core.models import GeneratedQuestionSet, User

    quiz = self.get_object()
    denied = (_review_guard(request.user, quiz) or _generation_ready_guard(quiz))
    if denied:
      return denied

    student = User.objects.filter(email=request.data.get('student')).first()
    if student is None or not isStudent(student, quiz.course):
      return Response({'error': 'No student with that email is enrolled in this course.'},
                      status=status.HTTP_400_BAD_REQUEST)
    submission = quiz_grading.latest_submission_for(student, quiz.assignment)
    if submission is None:
      return Response({'error': 'The student has no submission for this assignment to '
                                'generate from.'}, status=status.HTTP_400_BAD_REQUEST)

    force = bool(request.data.get('force'))
    gen_set, _ = GeneratedQuestionSet.objects.get_or_create(quiz=quiz, student=student)
    if gen_set.status == 'generating':
      return Response({'error': "The student's set is already generating."},
                      status=status.HTTP_400_BAD_REQUEST)
    if gen_set.status == 'approved' and not force:
      return Response({'error': "The student's set is already approved. Pass force=true to "
                                'regenerate it (this un-publishes the quiz for them until '
                                're-approval).'}, status=status.HTTP_400_BAD_REQUEST)
    gen_set.status = 'pending'
    gen_set.approvedBy = None
    gen_set.approvedAt = None
    gen_set.save(update_fields=['status', 'approvedBy', 'approvedAt', 'modified'])
    from core.tasks import generate_personalized_quiz_sets
    generate_personalized_quiz_sets.delay(
        submission.id, quiz_id=quiz.id, force=True,
        requested_by_id=request.user.id, student_id=student.id)
    record_audit_event(course=quiz.course, event_type='quiz_generated_set_regenerated',
                       user=request.user, quiz=quiz, assignment=quiz.assignment,
                       meta={'studentEmail': student.email, 'setId': gen_set.id,
                             'trigger': 'generateForStudent'})
    return Response(GeneratedQuestionSetSerializer(gen_set, context={'request': request}).data,
                    status=status.HTTP_202_ACCEPTED)

  @extend_schema(
      responses=inline_serializer('BackfillPreviewResponse', {
          'wouldGenerate': serializers.IntegerField(),
          'missing': serializers.IntegerField(),
      }),
  )
  @action(detail=True, methods=['GET'])
  def backfillPreview(self, request, pk=None):
    """How many students a backfill would touch — shown to the instructor before they
    save a new AI section (``wouldGenerate``: submitters minus approved sets, i.e. the
    section-create backfill) and on the review drawer's Generate-missing button
    (``missing``: submitters without any set)."""
    quiz = self.get_object()
    denied = _review_guard(request.user, quiz)
    if denied:
      return denied
    if quiz.assignment_id is None:
      return Response({'wouldGenerate': 0, 'missing': 0})
    from core.tasks import enqueue_personalized_backfill
    return Response({
        'wouldGenerate': enqueue_personalized_backfill(quiz, dry_run=True),
        'missing': enqueue_personalized_backfill(quiz, dry_run=True, missing_only=True),
    })

  @extend_schema(
      request=None,
      responses=inline_serializer('GenerateMissingResponse', {'queued': serializers.IntegerField()}),
  )
  @action(detail=True, methods=['POST'])
  def generateMissing(self, request, pk=None):
    """Queue question generation for every student who has a submission on the attached
    assignment but no question set yet — e.g. they submitted before the AI section
    existed, or the feature was off / generation failed at the time."""
    quiz = self.get_object()
    denied = (_review_guard(request.user, quiz) or _generation_ready_guard(quiz))
    if denied:
      return denied

    from core.tasks import enqueue_personalized_backfill
    queued = enqueue_personalized_backfill(quiz, requested_by_id=request.user.id,
                                           missing_only=True)
    if queued:
      record_audit_event(course=quiz.course, event_type='quiz_generated_set_regenerated',
                         user=request.user, quiz=quiz, assignment=quiz.assignment,
                         meta={'trigger': 'generateMissing', 'queued': queued})
    return Response({'queued': queued}, status=status.HTTP_202_ACCEPTED)

  @extend_schema(
      responses=inline_serializer('PromptVariable', {
          'token': serializers.CharField(), 'name': serializers.CharField(),
          'argument': serializers.CharField(allow_null=True), 'label': serializers.CharField(),
          'description': serializers.CharField(), 'kind': serializers.CharField()},
          many=True),
      description="The {variables} usable in this quiz's AI-generated section prompts "
                  "(powers the prompt editor's autocomplete).",
  )
  @action(detail=True, methods=['GET'])
  def promptVariables(self, request, pk=None):
    quiz = self.get_object()
    if not (request.user.is_superuser or isCourseStaff(request.user, quiz.course)):
      return Response({'detail': 'Only course staff can list prompt variables.'},
                      status=status.HTTP_403_FORBIDDEN)
    from core.prompts.variables import VariableContext, describe_available_variables
    return Response(describe_available_variables(
        VariableContext(course=quiz.course, assignment=quiz.assignment)))
