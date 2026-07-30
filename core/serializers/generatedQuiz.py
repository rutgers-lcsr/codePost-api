# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from typing import Optional

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
  datasetTruncationWarning = serializers.SerializerMethodField()

  class Meta:
    model = QuizGeneratedSection
    fields = ('id', 'quiz', 'name', 'systemPrompt', 'numQuestions', 'pointsPerQuestion',
              'questionTypes', 'sortKey', 'datasetTruncationWarning')
    POST_permissions_fields = ('quiz',)

  def get_datasetTruncationWarning(self, obj) -> Optional[str]:
    """Non-blocking authoring hint: if the prompt pulls in {student_dataset} and any active
    variant is larger than the prompt cap, the model won't see the whole file. Returns a
    message or None. Uses file size (bytes) as a proxy for character length."""
    from core.prompts.variables import STUDENT_DATASET_CHAR_CAP
    if 'student_dataset' not in (obj.systemPrompt or ''):
      return None
    assignment = getattr(obj.quiz, 'assignment', None)
    if assignment is None:
      return None
    oversized = 0
    for d in assignment.dataSets.filter(is_student_variant=True, is_active=True):
      try:
        if d.file and d.file.size > STUDENT_DATASET_CHAR_CAP:
          oversized += 1
      except Exception:
        continue
    if not oversized:
      return None
    return (f"{oversized} dataset variant(s) exceed the {STUDENT_DATASET_CHAR_CAP:,}-character "
            "prompt limit and will be truncated where {student_dataset} is inserted.")

  def validate(self, data):
    data = super().validate(data)
    proposed = self.genProposedFields(data)
    quiz = proposed.get('quiz')
    # Re-authorize the destination course: a PATCH could point `quiz` at another course's
    # quiz (object permissions only checked the source quiz's course).
    self.assert_authoring_course(quiz.course if quiz is not None else None)
    # Standalone quizzes may carry generated sections as long as the prompt doesn't draw
    # on assignment/submission data — validate_template below rejects each offending
    # {variable} with a helpful message when the quiz is unattached. Submission-free
    # prompts generate eagerly per student instead of waiting for a submission.
    # Block creating a section when the AI feature is off/unconfigured — otherwise
    # generation never runs and students sit at 'questions_not_ready' forever.
    # (Editing/deleting existing sections stays allowed for cleanup.)
    if self.instance is None and quiz is not None:
      from core.services.ai_service import AIService
      if not AIService(quiz.course, quiz.assignment).is_feature_enabled('personalized_quiz_generation'):
        raise serializers.ValidationError(
            "AI quiz question generation is not enabled for this course. Enable the "
            "'AI-Generated Quiz Questions' AI feature in the course's AI settings first.")
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
              'points', 'sortKey', 'language', 'starterCode', 'referenceSolution')
    read_only_fields = ('set', 'section')

  def validate_choicesData(self, value):
    if not isinstance(value, list) or any(
        not isinstance(c, dict) or 'text' not in c for c in value):
      raise serializers.ValidationError(
          "choicesData must be a list of {text, isCorrect, feedback} objects.")
    return [{'text': c.get('text', ''), 'isCorrect': bool(c.get('isCorrect')),
             'feedback': c.get('feedback', '') or ''} for c in value]

  def validate(self, data):
    data = super().validate(data)
    # A reviewer edit must not strip the answer key from an auto-graded question — a
    # keyless question grades every student wrong. Only enforced when the edit touches
    # the key (choicesData/questionType), matching QuestionSerializer.
    if 'choicesData' in data or 'questionType' in data:
      from core.services.quiz_grading import has_answer_key
      proposed = self.genProposedFields(data)
      if not has_answer_key(proposed.get('questionType'), proposed.get('choicesData')):
        raise serializers.ValidationError(
            {'choicesData': 'At least one choice must be marked correct for this question type.'})
    return data


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
