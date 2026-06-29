# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.serializers.quizQuestionGroup import QuizQuestionGroupSerializer
from core.models import Quiz, QuizQuestion


class QuizQuestionSerializer(ModelSerializerWithPOSTCheck):
  """Membership of a Question in a Quiz, with ordering and optional point override."""

  class Meta:
    model = QuizQuestion
    fields = ('id', 'quiz', 'question', 'sortKey', 'pointsOverride')
    POST_permissions_fields = ('quiz',)


class QuizSerializer(ModelSerializerWithPOSTCheck):
  quizQuestions = QuizQuestionSerializer(many=True, read_only=True)
  questionGroups = QuizQuestionGroupSerializer(many=True, read_only=True)

  class Meta:
    model = Quiz
    fields = (
        'id', 'course', 'assignment', 'title', 'description',
        # Availability
        'assignmentTrigger', 'availableFrom', 'availableUntil',
        # Standard options
        'timeLimitMinutes', 'attemptsAllowed', 'shuffleQuestions',
        'showCorrectAnswers', 'passingScore', 'passingScoreUnit', 'isPublished',
        'quizQuestions', 'questionGroups', 'source', 'createdBy', 'metadata',
    )
    read_only_fields = ('source', 'createdBy', 'metadata', 'quizQuestions', 'questionGroups')
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
    return data

  def create(self, validated_data):
    request = self.context.get('request')
    if request is not None and validated_data.get('createdBy') is None:
      validated_data['createdBy'] = request.user
    return super().create(validated_data)
