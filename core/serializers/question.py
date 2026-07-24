# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Question, QuestionChoice
from core.services import quiz_grading


class QuestionChoiceSerializer(serializers.ModelSerializer):
  # ``id`` is accepted (but not required) so clients can round-trip existing choices.
  id = serializers.IntegerField(required=False)

  class Meta:
    model = QuestionChoice
    fields = ('id', 'text', 'isCorrect', 'sortKey', 'feedback')


class QuestionSerializer(ModelSerializerWithPOSTCheck):
  """A quiz question that lives in exactly one bank, with nested writable choices.

  Choices are synced atomically on create/update — a question and its options are
  authored as a unit (a multiple-choice question is meaningless without them).
  """
  choices = QuestionChoiceSerializer(many=True, required=False)

  class Meta:
    model = Question
    fields = (
        'id', 'course', 'bank', 'questionType', 'text', 'description', 'points', 'generalFeedback',
        'partialCredit', 'numericTolerance',
        'language', 'starterCode', 'referenceSolution', 'source', 'createdBy',
        'choices', 'metadata',
    )
    read_only_fields = ('source', 'createdBy', 'metadata')
    POST_permissions_fields = ('course',)

  def validate(self, data):
    data = super().validate(data)
    # Merge with the existing instance so a PATCH that sends ONLY `bank` (course omitted)
    # still runs the check — otherwise a question can be silently moved into another
    # course's bank, bypassing the object-permission check that ran against the old course.
    proposed = self.genProposedFields(data)
    bank = proposed.get('bank')
    course = proposed.get('course')
    if bank is not None and course is not None and bank.course_id != course.id:
      raise serializers.ValidationError({'bank': 'Bank does not belong to this course.'})
    tolerance = proposed.get('numericTolerance')
    if tolerance is not None and tolerance < 0:
      raise serializers.ValidationError(
          {'numericTolerance': 'numericTolerance cannot be negative.'})
    # An auto-graded question with no choice marked correct grades every student wrong
    # (grade_response treats an empty key as never-correct) — reject it while the key is
    # being shaped (create, or an update touching choices/questionType). Unrelated edits
    # to pre-existing rows are left alone, mirroring the seal guard in QuizSerializer.
    if self.instance is None or 'choices' in data or 'questionType' in data:
      qtype = proposed.get('questionType') or 'multiple_choice'
      choices = data.get('choices')
      if choices is None and self.instance is not None:
        choices = list(self.instance.choices.all())
      if not quiz_grading.has_answer_key(qtype, choices):
        raise serializers.ValidationError(
            {'choices': 'At least one choice must be marked correct for this question type.'})
    return data

  def _sync_choices(self, question, choices_data):
    question.choices.all().delete()
    for i, c in enumerate(choices_data):
      c.pop('id', None)
      question.choices.create(
          text=c.get('text', ''),
          isCorrect=c.get('isCorrect', False),
          sortKey=c.get('sortKey', i),
          feedback=c.get('feedback', '') or '',
      )

  def create(self, validated_data):
    choices_data = validated_data.pop('choices', [])
    request = self.context.get('request')
    if request is not None and validated_data.get('createdBy') is None:
      validated_data['createdBy'] = request.user
    question = Question.objects.create(**validated_data)
    self._sync_choices(question, choices_data)
    return question

  def update(self, instance, validated_data):
    choices_data = validated_data.pop('choices', None)
    for attr, value in validated_data.items():
      setattr(instance, attr, value)
    # Keep course consistent if the bank changed.
    if 'bank' in validated_data:
      instance.course = instance.bank.course
    instance.save()
    if choices_data is not None:
      self._sync_choices(instance, choices_data)
    return instance
