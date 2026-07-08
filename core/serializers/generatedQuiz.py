# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import (
    GeneratedQuestionSet, GeneratedQuizQuestion, QuizGeneratedSection, QUESTION_TYPE_CHOICES,
)


class QuizGeneratedSectionSerializer(ModelSerializerWithPOSTCheck):
  """A per-student generation config on a quiz: an instructor-authored prompt template,
  question count, and points per question. The prompt is strictly validated on save
  (unknown {variables} are rejected with helpful messages)."""

  questionTypes = serializers.JSONField(required=False)

  class Meta:
    model = QuizGeneratedSection
    fields = ('id', 'quiz', 'name', 'systemPrompt', 'numQuestions', 'pointsPerQuestion',
              'questionTypes', 'sortKey')
    POST_permissions_fields = ('quiz',)

  def validate(self, data):
    data = super().validate(data)
    proposed = self.genProposedFields(data)
    quiz = proposed.get('quiz')
    # Generation is seeded by the student's submission, so the quiz must be attached.
    if quiz is not None and quiz.assignment_id is None:
      raise serializers.ValidationError(
          "Personalized sections require the quiz to be attached to an assignment.")
    if proposed.get('numQuestions') is not None and proposed['numQuestions'] < 1:
      raise serializers.ValidationError("numQuestions must be at least 1.")
    question_types = proposed.get('questionTypes') or []
    valid_types = {key for key, _ in QUESTION_TYPE_CHOICES}
    if not isinstance(question_types, list) or any(t not in valid_types for t in question_types):
      raise serializers.ValidationError(
          f"questionTypes must be a list of question type keys ({', '.join(sorted(valid_types))}).")
    system_prompt = proposed.get('systemPrompt')
    if system_prompt is not None and quiz is not None:
      from core.prompts.variables import VariableContext, validate_template
      errors = validate_template(system_prompt, VariableContext(
          course=quiz.course, assignment=quiz.assignment))
      if errors:
        raise serializers.ValidationError({'systemPrompt': errors})
    return data


class GeneratedQuizQuestionSerializer(ModelSerializerWithPOSTCheck):
  """One generated question in a student's set. Staff may edit its content (PATCH)
  before or after approval; the set/section links are system-managed."""

  choicesData = serializers.JSONField(required=False)

  class Meta:
    model = GeneratedQuizQuestion
    fields = ('id', 'set', 'section', 'questionType', 'text', 'description', 'choicesData',
              'points', 'sortKey', 'language', 'starterCode')
    read_only_fields = ('set', 'section')

  def validate_choicesData(self, value):
    if not isinstance(value, list) or any(
        not isinstance(c, dict) or 'text' not in c for c in value):
      raise serializers.ValidationError(
          "choicesData must be a list of {text, isCorrect, feedback} objects.")
    return [{'text': c.get('text', ''), 'isCorrect': bool(c.get('isCorrect')),
             'feedback': c.get('feedback', '') or ''} for c in value]


class GeneratedQuestionSetSerializer(serializers.ModelSerializer):
  """A student's generated question set with its questions — the review payload.
  Staff-only (never exposed to students)."""

  studentEmail = serializers.EmailField(source='student.email', read_only=True)
  approvedByEmail = serializers.EmailField(source='approvedBy.email', read_only=True,
                                           allow_null=True)
  questions = GeneratedQuizQuestionSerializer(many=True, read_only=True)

  class Meta:
    model = GeneratedQuestionSet
    fields = ('id', 'quiz', 'student', 'studentEmail', 'submission', 'status',
              'approvedBy', 'approvedByEmail', 'approvedAt', 'errorMessage',
              'generationMetadata', 'questions', 'created', 'modified')
    read_only_fields = fields


class GeneratedQuestionSetListSerializer(serializers.ModelSerializer):
  """Summary row for the per-quiz review table (no question payload)."""

  studentEmail = serializers.EmailField(source='student.email', read_only=True)
  questionCount = serializers.SerializerMethodField()

  class Meta:
    model = GeneratedQuestionSet
    fields = ('id', 'quiz', 'student', 'studentEmail', 'submission', 'status',
              'approvedAt', 'errorMessage', 'questionCount', 'created', 'modified')
    read_only_fields = fields

  def get_questionCount(self, obj) -> int:
    return obj.questions.count()
