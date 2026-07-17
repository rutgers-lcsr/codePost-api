# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.serializers.quizQuestionGroup import QuizQuestionGroupSerializer
from core.serializers.generatedQuiz import QuizGeneratedSectionSerializer
from core.models import Quiz, QuizQuestion
from core.services import quiz_grading


class QuizQuestionSerializer(ModelSerializerWithPOSTCheck):
  """Membership of a Question in a Quiz, with ordering and optional point override."""

  class Meta:
    model = QuizQuestion
    fields = ('id', 'quiz', 'question', 'sortKey', 'pointsOverride')
    POST_permissions_fields = ('quiz',)

  def validate(self, data):
    data = super().validate(data)
    proposed = self.genProposedFields(data)
    quiz = proposed.get('quiz')
    question = proposed.get('question')
    # The attached question must belong to the same course as the quiz (mirrors the bank
    # check in QuizQuestionGroupSerializer) — otherwise another course's question, and its
    # content, could be surfaced to this quiz's students.
    if quiz is not None and question is not None and question.course_id != quiz.course_id:
      raise serializers.ValidationError("The question must belong to the same course as the quiz.")
    return data


class QuizSerializer(ModelSerializerWithPOSTCheck):
  quizQuestions = QuizQuestionSerializer(many=True, read_only=True)
  questionGroups = QuizQuestionGroupSerializer(many=True, read_only=True)
  generatedSections = QuizGeneratedSectionSerializer(many=True, read_only=True)

  class Meta:
    model = Quiz
    fields = (
        'id', 'course', 'assignment', 'title', 'description',
        # Availability
        'assignmentTrigger', 'availableFrom', 'availableUntil',
        'closeEvent', 'closeOffsetMinutes', 'endAttemptsAtClose',
        # Standard options
        'timeLimitMinutes', 'attemptsAllowed', 'shuffleQuestions',
        'oneQuestionAtATime', 'allowBacktracking',
        'showCorrectAnswers', 'showResponses', 'passingScore', 'passingScoreUnit', 'scoringPolicy',
        'multiAttemptScoreMethod', 'isPublished',
        # Per-student generated questions
        'gradersCanReviewGenerated', 'autoPublishGenerated', 'generatedSections',
        'quizQuestions', 'questionGroups', 'source', 'createdBy', 'metadata',
    )
    read_only_fields = ('source', 'createdBy', 'metadata', 'quizQuestions', 'questionGroups',
                        'generatedSections')
    POST_permissions_fields = ('course',)

  def validate(self, data):
    data = super().validate(data)
    proposed = self.genProposedFields(data)
    # Standalone availability window must be ordered (the trigger governs attached quizzes,
    # but validate the window whenever both ends are set).
    available_from = proposed.get('availableFrom')
    available_until = proposed.get('availableUntil')
    if available_from and available_until and available_from >= available_until:
      raise serializers.ValidationError("availableUntil must be after availableFrom.")
    # Passing score: never negative; capped at 100 only when expressed as a percent.
    passing_score = proposed.get('passingScore')
    if passing_score is not None:
      if passing_score < 0:
        raise serializers.ValidationError("passingScore cannot be negative.")
      if proposed.get('passingScoreUnit') == 'percent' and passing_score > 100:
        raise serializers.ValidationError("passingScore cannot exceed 100 when expressed as a percent.")
    # A close anchored on the same moment the quiz opens needs a positive offset, or it
    # would close the instant it opens.
    if proposed.get('assignment') is not None and (proposed.get('closeOffsetMinutes') or 0) == 0:
      degenerate = (proposed.get('assignmentTrigger'), proposed.get('closeEvent')) in {
          ('after_submission', 'submission'),
          ('after_feedback', 'feedback_released'),
          ('after_assignment', 'assignment_due'),
      }
      if degenerate:
        raise serializers.ValidationError(
            "Set a duration for the close — it would otherwise close the moment the quiz opens.")
    # Generated sections whose prompts draw on assignment/submission data are seeded by
    # the attached assignment; detaching or re-attaching would orphan them (and any
    # per-student sets). Submission-free sections don't depend on the assignment, so the
    # quiz may attach/detach freely.
    if self.instance is not None and 'assignment' in data \
        and data.get('assignment') != self.instance.assignment \
        and self.instance.generatedSections.exists():
      from core.prompts.variables import template_requirements
      if any('assignment' in template_requirements(s.systemPrompt)
             for s in self.instance.generatedSections.all()):
        raise serializers.ValidationError(
            "This quiz has personalized question sections whose prompts use assignment or "
            "submission {variables} — remove those sections (or those variables) before "
            "changing the attached assignment.")
    return data

  def create(self, validated_data):
    request = self.context.get('request')
    if request is not None and validated_data.get('createdBy') is None:
      validated_data['createdBy'] = request.user
    return super().create(validated_data)

  def update(self, instance, validated_data):
    # Existing attempts bake in the passing threshold (stored passed) and the deadline
    # (stored at start). Snapshot the fields they depend on and reflect any change onto
    # those attempts, so edited settings apply retroactively instead of leaving stale state.
    watched = quiz_grading.PASSING_FIELDS | quiz_grading.DEADLINE_FIELDS
    old = {f: getattr(instance, f) for f in watched}
    instance = super().update(instance, validated_data)
    changed = {f for f in watched if getattr(instance, f) != old[f]}
    if changed:
      quiz_grading.sync_attempts_to_settings(instance, changed)
    return instance
