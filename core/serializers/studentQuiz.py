# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""Student-facing quiz serializers. These NEVER expose provenance (source/createdBy/metadata)
and hide correct answers / per-choice feedback / scores until the reveal context allows it.

Context flags (set by the view):
  reveal       — correct answers + per-choice/question feedback + per-response correctness may show.
  revealScore  — the attempt's numeric score / pass-fail may show (i.e. it has been submitted).
"""
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.models import Question, QuestionChoice, Quiz, QuizAttempt, QuizResponse
from core.services import quiz_grading


class QuizAvailabilitySerializer(serializers.Serializer):
  """Shape of StudentQuiz.availability (documents the SerializerMethodField for the client)."""
  isOpen = serializers.BooleanField()
  reason = serializers.CharField()


class StudentQuestionChoiceSerializer(serializers.ModelSerializer):
  class Meta:
    model = QuestionChoice
    fields = ('id', 'text', 'sortKey', 'isCorrect', 'feedback')

  def to_representation(self, instance):
    data = super().to_representation(instance)
    if not self.context.get('reveal'):
      data.pop('isCorrect', None)
      data.pop('feedback', None)
    return data


class StudentQuestionSerializer(serializers.ModelSerializer):
  """A question as a student sees it — no provenance; correct answers gated by `reveal`."""
  choices = StudentQuestionChoiceSerializer(many=True, read_only=True)

  class Meta:
    model = Question
    fields = ('id', 'questionType', 'text', 'description', 'starterCode', 'language',
              'choices', 'generalFeedback')

  def to_representation(self, instance):
    data = super().to_representation(instance)
    if not self.context.get('reveal'):
      data.pop('generalFeedback', None)
    return data


class StudentQuizResponseSerializer(serializers.ModelSerializer):
  question = StudentQuestionSerializer(read_only=True)
  selectedChoices = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

  class Meta:
    model = QuizResponse
    fields = ('id', 'question', 'sortKey', 'points', 'answerText', 'selectedChoices',
              'pointsEarned', 'isCorrect', 'needsManualGrading', 'graderFeedback')

  def to_representation(self, instance):
    data = super().to_representation(instance)
    if not self.context.get('reveal'):
      data.pop('pointsEarned', None)
      data.pop('isCorrect', None)
      data.pop('graderFeedback', None)
    return data


class StudentQuizAttemptSerializer(serializers.ModelSerializer):
  responses = StudentQuizResponseSerializer(many=True, read_only=True)
  # Navigation mode is denormalized from the quiz so the taking UI doesn't need a second fetch.
  oneQuestionAtATime = serializers.BooleanField(source='quiz.oneQuestionAtATime', read_only=True)
  allowBacktracking = serializers.BooleanField(source='quiz.allowBacktracking', read_only=True)
  # The server's current time at response, so the client can run a skew-immune countdown
  # (it measures elapsed time locally from this anchor rather than trusting the device clock).
  serverNow = serializers.SerializerMethodField()

  class Meta:
    model = QuizAttempt
    fields = ('id', 'quiz', 'attemptNumber', 'status', 'startedAt', 'deadline',
              'submittedAt', 'score', 'maxScore', 'needsManualGrading', 'passed',
              'oneQuestionAtATime', 'allowBacktracking', 'serverNow', 'responses')

  @extend_schema_field(serializers.DateTimeField())
  def get_serverNow(self, obj):
    return timezone.now().isoformat()

  def to_representation(self, instance):
    data = super().to_representation(instance)
    if not self.context.get('revealScore'):
      for key in ('score', 'maxScore', 'passed'):
        data.pop(key, None)
    return data


class StudentQuizSerializer(serializers.ModelSerializer):
  """Summary of a quiz for a student: settings, availability, and the caller's attempt usage."""
  questionCount = serializers.SerializerMethodField()
  availability = serializers.SerializerMethodField()
  attemptsUsed = serializers.SerializerMethodField()
  hasOpenAttempt = serializers.SerializerMethodField()
  hasSubmittedAttempt = serializers.SerializerMethodField()
  closeAt = serializers.SerializerMethodField()

  class Meta:
    model = Quiz
    fields = ('id', 'course', 'assignment', 'title', 'description', 'timeLimitMinutes',
              'attemptsAllowed', 'scoringPolicy', 'passingScore', 'passingScoreUnit',
              'showCorrectAnswers', 'questionCount', 'availability', 'attemptsUsed',
              'hasOpenAttempt', 'hasSubmittedAttempt', 'closeAt')

  @extend_schema_field(serializers.IntegerField())
  def get_questionCount(self, obj):
    # Fixed questions plus how many each random draw will present.
    count = obj.quizQuestions.count()
    for group in obj.questionGroups.select_related('bank').all():
      count += min(group.pickCount, group.bank.questions.count())
    return count

  def _student(self):
    request = self.context.get('request')
    return request.user if request is not None else None

  @extend_schema_field(QuizAvailabilitySerializer)
  def get_availability(self, obj):
    is_open, reason = quiz_grading.quiz_availability(obj, self._student())
    return {'isOpen': is_open, 'reason': reason}

  @extend_schema_field(serializers.IntegerField())
  def get_attemptsUsed(self, obj):
    student = self._student()
    if student is None:
      return 0
    return obj.attempts.filter(student=student).count()

  @extend_schema_field(serializers.BooleanField())
  def get_hasOpenAttempt(self, obj):
    student = self._student()
    return student is not None and obj.attempts.filter(student=student, status='in_progress').exists()

  @extend_schema_field(serializers.BooleanField())
  def get_hasSubmittedAttempt(self, obj):
    student = self._student()
    return student is not None and obj.attempts.filter(student=student, status='submitted').exists()

  @extend_schema_field(serializers.DateTimeField(allow_null=True))
  def get_closeAt(self, obj):
    return quiz_grading.quiz_close_time(obj, self._student())


class StaffQuizAttemptSerializer(StudentQuizAttemptSerializer):
  """A quiz attempt as staff (grading) sees it: the student's identity plus every response
  with answers and grading state. Callers set reveal/revealScore context to True."""
  student = serializers.SlugRelatedField(slug_field='email', read_only=True)

  class Meta(StudentQuizAttemptSerializer.Meta):
    fields = StudentQuizAttemptSerializer.Meta.fields + ('student',)
