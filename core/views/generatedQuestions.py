# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import GeneratedQuestionSet, GeneratedQuizQuestion, QuizGeneratedSection
from core.serializers.generatedQuiz import (
    GeneratedQuestionSetSerializer, GeneratedQuizQuestionSerializer,
    QuizGeneratedSectionSerializer,
)
from core.services.audit import record_audit_event
from core.views.template import ListProtectedViewSet
from core.permissions.permissions import (
    GeneratedQuestionSetPermissions, GeneratedQuizQuestionPermissions,
    QuizGeneratedSectionPermissions,
)

from logging import getLogger
logger = getLogger(__name__)

# Statuses in which a set's questions exist and may be staff-edited.
EDITABLE_SET_STATUSES = ('ready', 'approved')

# How long a set may sit in 'generating' before the claim is presumed dead (a worker that
# crashed without writing back). Tasks have no retries, so without this the set would be
# stuck forever — every generate/regenerate action refusing with "already generating".
# Comfortably above a real multi-section run; a superseded zombie that later completes is
# discarded by the generationBatch protocol. (Same idea as runCode's stale-run window.)
GENERATING_STALE_AFTER = timedelta(minutes=10)


def generating_is_stale(gen_set, now=None):
  """Whether a 'generating' claim is old enough to be presumed dead and reclaimable."""
  return ((now or timezone.now()) - gen_set.modified) > GENERATING_STALE_AFTER


class QuizGeneratedSectionViewSet(ListProtectedViewSet):
  """Per-student generation configs on a quiz (authoring, course staff).

  A section's ``systemPrompt`` template is validated on save; the variables it may use
  are listed by ``GET /quizzes/{id}/promptVariables/``.
  """
  queryset = QuizGeneratedSection.objects.select_related(
      'quiz', 'quiz__course', 'quiz__assignment').all()
  serializer_class = QuizGeneratedSectionSerializer
  permission_classes = (IsAuthenticated, QuizGeneratedSectionPermissions)


class GeneratedQuestionSetViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
  """A student's generated question set — the review unit. System-created by the
  generation task (never via POST); staff approve/unapprove/regenerate here and list
  them per quiz via ``GET /quizzes/{id}/generatedSets/``. Staff-only."""
  queryset = GeneratedQuestionSet.objects.select_related(
      'quiz', 'quiz__course', 'student', 'approvedBy', 'submission').prefetch_related(
      'questions').all()
  serializer_class = GeneratedQuestionSetSerializer
  permission_classes = (IsAuthenticated, GeneratedQuestionSetPermissions)

  @extend_schema(
      request=None, responses=GeneratedQuestionSetSerializer,
      description="Approve this student's generated questions — their quiz opens once "
                  "approved. The approving staff member takes authorship of the questions.",
  )
  @action(detail=True, methods=['POST'])
  def approve(self, request, pk=None):
    gen_set = self.get_object()
    if gen_set.status not in EDITABLE_SET_STATUSES:
      return Response({'error': f'The set is {gen_set.status} — it must be ready for review.'},
                      status=status.HTTP_400_BAD_REQUEST)
    if not gen_set.questions.exists():
      return Response({'error': 'The set has no questions to approve.'},
                      status=status.HTTP_400_BAD_REQUEST)
    gen_set.status = 'approved'
    gen_set.approvedBy = request.user
    gen_set.approvedAt = timezone.now()
    gen_set.save(update_fields=['status', 'approvedBy', 'approvedAt', 'modified'])
    record_audit_event(course=gen_set.quiz.course, event_type='quiz_generated_set_approved',
                       user=request.user, quiz=gen_set.quiz, assignment=gen_set.quiz.assignment,
                       meta={'studentEmail': gen_set.student.email, 'setId': gen_set.id})
    return Response(self.get_serializer(gen_set).data)

  @extend_schema(
      request=None, responses=GeneratedQuestionSetSerializer,
      description="Take an approved set back to review (closing the quiz for that student). "
                  "Blocked once the student has any attempt on the quiz.",
  )
  @action(detail=True, methods=['POST'])
  def unapprove(self, request, pk=None):
    gen_set = self.get_object()
    if gen_set.status != 'approved':
      return Response({'error': 'Only approved sets can be unapproved.'},
                      status=status.HTTP_400_BAD_REQUEST)
    if gen_set.quiz.attempts.filter(student=gen_set.student).exists():
      return Response({'error': 'The student has already attempted this quiz.'},
                      status=status.HTTP_400_BAD_REQUEST)
    gen_set.status = 'ready'
    gen_set.approvedBy = None
    gen_set.approvedAt = None
    gen_set.save(update_fields=['status', 'approvedBy', 'approvedAt', 'modified'])
    record_audit_event(course=gen_set.quiz.course, event_type='quiz_generated_set_unapproved',
                       user=request.user, quiz=gen_set.quiz, assignment=gen_set.quiz.assignment,
                       meta={'studentEmail': gen_set.student.email, 'setId': gen_set.id})
    return Response(self.get_serializer(gen_set).data)

  @extend_schema(
      request=None, responses=GeneratedQuestionSetSerializer,
      description="Discard this set's questions and generate new ones from the student's "
                  "submission. An approved set becomes un-published until re-approved. "
                  "Blocked once the student has attempted the quiz — their responses "
                  "reference these questions (the grading answer key).",
  )
  @action(detail=True, methods=['POST'])
  def regenerate(self, request, pk=None):
    from core.services.quiz_grading import generation_needs_submission
    gen_set = self.get_object()
    # Submission-free prompts regenerate without a seed submission (the eager path).
    if gen_set.submission_id is None and generation_needs_submission(gen_set.quiz):
      return Response({'error': 'The set has no submission to regenerate from.'},
                      status=status.HTTP_400_BAD_REQUEST)
    if gen_set.status == 'generating' and not generating_is_stale(gen_set):
      return Response({'error': 'The set is already generating.'},
                      status=status.HTTP_400_BAD_REQUEST)
    # Regenerating deletes the current questions; a submitted attempt's grading key
    # (referenceSolution) lives on them, so it would be severed for graders. Mirrors the
    # unapprove guard.
    if gen_set.questions.exists() and gen_set.quiz.attempts.filter(student=gen_set.student).exists():
      return Response({'error': 'The student has already attempted this quiz — reset their '
                                'attempts before regenerating their questions.'},
                      status=status.HTTP_400_BAD_REQUEST)
    gen_set.status = 'pending'
    gen_set.approvedBy = None
    gen_set.approvedAt = None
    gen_set.save(update_fields=['status', 'approvedBy', 'approvedAt', 'modified'])
    from core.tasks import generate_personalized_quiz_sets
    if gen_set.submission_id is not None:
      generate_personalized_quiz_sets.delay(
          gen_set.submission_id, quiz_id=gen_set.quiz_id, force=True,
          requested_by_id=request.user.id, student_id=gen_set.student_id)
    else:
      generate_personalized_quiz_sets.delay(
          quiz_id=gen_set.quiz_id, student_id=gen_set.student_id, force=True,
          requested_by_id=request.user.id)
    record_audit_event(course=gen_set.quiz.course, event_type='quiz_generated_set_regenerated',
                       user=request.user, quiz=gen_set.quiz, assignment=gen_set.quiz.assignment,
                       meta={'studentEmail': gen_set.student.email, 'setId': gen_set.id})
    return Response(self.get_serializer(gen_set).data, status=status.HTTP_202_ACCEPTED)


class GeneratedQuizQuestionViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                                   mixins.DestroyModelMixin, viewsets.GenericViewSet):
  """One generated question in a student's set. Staff PATCH-edit content inline during
  review (no regeneration needed) or DELETE a bad question; edits after approval are
  fine — started attempts are snapshot-isolated."""
  queryset = GeneratedQuizQuestion.objects.select_related(
      'set', 'set__quiz', 'set__quiz__course', 'section').all()
  serializer_class = GeneratedQuizQuestionSerializer
  permission_classes = (IsAuthenticated, GeneratedQuizQuestionPermissions)

  def _set_editable(self, obj):
    if obj.set.status not in EDITABLE_SET_STATUSES:
      return Response({'error': f'The set is {obj.set.status} — its questions cannot be edited.'},
                      status=status.HTTP_400_BAD_REQUEST)
    return None

  def update(self, request, *args, **kwargs):
    blocked = self._set_editable(self.get_object())
    return blocked if blocked is not None else super().update(request, *args, **kwargs)

  def destroy(self, request, *args, **kwargs):
    obj = self.get_object()
    blocked = self._set_editable(obj)
    if blocked is not None:
      return blocked
    # Deleting the question severs the grading answer key (referenceSolution) that a
    # submitted attempt's manual grading reads off the live row. Mirrors the regenerate/
    # unapprove guards; edits are left alone (started attempts are snapshot-isolated).
    if obj.set.quiz.attempts.filter(student=obj.set.student).exists():
      return Response({'error': 'The student has already attempted this quiz — reset their '
                                'attempts before deleting their questions.'},
                      status=status.HTTP_400_BAD_REQUEST)
    return super().destroy(request, *args, **kwargs)
