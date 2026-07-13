# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Student-facing quiz serializers. These NEVER expose provenance (source/createdBy/metadata)
and hide correct answers / per-choice feedback / scores until the reveal context allows it.

Context flags (set by the view):
  reveal       — correct answers + per-choice/question feedback + per-response correctness may show.
  revealScore  — the attempt's numeric score / pass-fail may show (i.e. it has been submitted).
"""
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.models import Quiz, QuizAttempt, QuizResponse
from core.services import quiz_grading

# Matches QuizAttempt.score/maxScore so method-field output renders like the model fields
# (string-coerced decimals) instead of raw Decimals becoming JSON floats.
_SCORE_FIELD = serializers.DecimalField(max_digits=8, decimal_places=2)


def serialize_score(value):
  """Render a score the way the attempt serializer's Decimal model fields do."""
  return _SCORE_FIELD.to_representation(value) if value is not None else None


def staff_reveal_context(request):
  """Serializer context for staff grading views: full answer + score reveal."""
  return {'request': request, 'reveal': True, 'revealScore': True}


class QuizAvailabilitySerializer(serializers.Serializer):
  """Shape of StudentQuiz.availability (documents the SerializerMethodField for the client)."""
  isOpen = serializers.BooleanField()
  reason = serializers.CharField()


# Types whose choices ARE selectable options (safe to show). For short_answer/numerical the
# "choices" are the accepted answers, and for essay/code there are none — so we never send
# choices for those types until `reveal`, or the answer key would leak mid-attempt.
SELECTABLE_TYPES = frozenset({'multiple_choice', 'multiple_answers', 'true_false'})


class StudentQuestionChoiceSerializer(serializers.Serializer):
  """Shape of a rendered snapshot choice for a student (documents the client contract)."""
  id = serializers.IntegerField()
  text = serializers.CharField()
  sortKey = serializers.IntegerField()
  isCorrect = serializers.BooleanField(required=False)
  feedback = serializers.CharField(required=False)


class StudentQuestionSerializer(serializers.Serializer):
  """Shape of a rendered snapshot question for a student (documents the client contract)."""
  id = serializers.IntegerField(allow_null=True)
  questionType = serializers.CharField()
  text = serializers.CharField()
  description = serializers.CharField(allow_null=True)
  starterCode = serializers.CharField(allow_null=True)
  language = serializers.CharField(allow_null=True)
  choices = StudentQuestionChoiceSerializer(many=True, required=False)
  generalFeedback = serializers.CharField(required=False, allow_null=True)


def render_question_snapshot(snap, reveal):
  """Render a stored questionSnapshot as a student sees it — no provenance. Correct answers /
  per-choice feedback / general feedback show only when `reveal`; choices are omitted entirely
  for non-selectable types pre-reveal (their choice text is the accepted answer)."""
  snap = snap or {}
  qtype = snap.get('type')
  data = {
      'id': snap.get('questionId'),
      'questionType': qtype,
      'text': snap.get('text'),
      'description': snap.get('description'),
      'starterCode': snap.get('starterCode'),
      'language': snap.get('language'),
  }
  if reveal:
    data['generalFeedback'] = snap.get('generalFeedback')
    data['choices'] = [
        {'id': c['id'], 'text': c['text'], 'sortKey': c.get('sortKey', 0),
         'isCorrect': c.get('isCorrect'), 'feedback': c.get('feedback')}
        for c in snap.get('choices', [])
    ]
  elif qtype in SELECTABLE_TYPES:
    data['choices'] = [
        {'id': c['id'], 'text': c['text'], 'sortKey': c.get('sortKey', 0)}
        for c in snap.get('choices', [])
    ]
  return data


class StudentQuizResponseSerializer(serializers.ModelSerializer):
  question = serializers.SerializerMethodField()
  selectedChoices = serializers.SerializerMethodField()

  class Meta:
    model = QuizResponse
    fields = ('id', 'question', 'sortKey', 'points', 'answerText', 'selectedChoices',
              'pointsEarned', 'isCorrect', 'needsManualGrading', 'graderFeedback')

  @extend_schema_field(StudentQuestionSerializer)
  def get_question(self, obj):
    return render_question_snapshot(obj.questionSnapshot, bool(self.context.get('reveal')))

  @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
  def get_selectedChoices(self, obj):
    # Ids into questionSnapshot.choices (kept named `selectedChoices` for client compatibility).
    return obj.selectedChoiceKeys or []

  def to_representation(self, instance):
    data = super().to_representation(instance)
    # Correctness follows the quiz's answer-reveal policy; the student's own earned points
    # and grader feedback are not answer keys, so they show as soon as scores do (i.e.
    # once the attempt is submitted) — even on showCorrectAnswers='never' quizzes.
    if not self.context.get('reveal'):
      data.pop('isCorrect', None)
    if not self.context.get('revealScore'):
      data.pop('pointsEarned', None)
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
  myScore = serializers.SerializerMethodField()
  myMaxScore = serializers.SerializerMethodField()
  myPassed = serializers.SerializerMethodField()
  myScorePending = serializers.SerializerMethodField()

  class Meta:
    model = Quiz
    fields = ('id', 'course', 'assignment', 'title', 'description', 'timeLimitMinutes',
              'attemptsAllowed', 'scoringPolicy', 'passingScore', 'passingScoreUnit',
              'showCorrectAnswers', 'questionCount', 'availability', 'attemptsUsed',
              'hasOpenAttempt', 'hasSubmittedAttempt', 'closeAt',
              'myScore', 'myMaxScore', 'myPassed', 'myScorePending')

  @extend_schema_field(serializers.IntegerField())
  def get_questionCount(self, obj):
    # Fixed questions plus how many each random draw will present.
    count = obj.quizQuestions.count()
    for group in obj.questionGroups.select_related('bank').all():
      count += min(group.pickCount, group.bank.questions.count())
    # Generated sections: this student's approved set's real count when it exists,
    # else each section's configured count (never any provenance).
    if obj.generatedSections.exists():
      student = self._student()
      gen_set = (obj.generatedSets.filter(student=student, status='approved').first()
                 if student is not None else None)
      if gen_set is not None:
        count += gen_set.questions.count()
      else:
        count += sum(s.numQuestions for s in obj.generatedSections.all())
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

  def _official_score(self, obj):
    # Cached per (serializer, quiz) so myScore/myMaxScore don't query twice.
    cache = getattr(self, '_official_score_cache', None)
    if cache is None:
      cache = self._official_score_cache = {}
    if obj.pk not in cache:
      student = self._student()
      cache[obj.pk] = quiz_grading.official_score(obj, student) if student is not None else None
    return cache[obj.pk]

  @extend_schema_field(serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True))
  def get_myScore(self, obj):
    """The caller's official score per scoringPolicy; null until a fully graded attempt exists."""
    official = self._official_score(obj)
    return serialize_score(official[0]) if official is not None else None

  @extend_schema_field(serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True))
  def get_myMaxScore(self, obj):
    official = self._official_score(obj)
    return serialize_score(official[1]) if official is not None else None

  @extend_schema_field(serializers.BooleanField(allow_null=True))
  def get_myPassed(self, obj):
    """Pass/fail of the official score; null when no threshold or no graded attempt."""
    official = self._official_score(obj)
    if official is None:
      return None
    return quiz_grading.official_passed(obj, self._student(), official=official)

  @extend_schema_field(serializers.BooleanField())
  def get_myScorePending(self, obj):
    """True while any of the caller's submitted attempts awaits manual grading."""
    student = self._student()
    return student is not None and obj.attempts.filter(
        student=student, status='submitted', needsManualGrading=True).exists()


class StaffQuizAttemptSerializer(StudentQuizAttemptSerializer):
  """A quiz attempt as staff (grading) sees it: the student's identity plus every response
  with answers and grading state. Callers set reveal/revealScore context to True."""
  student = serializers.SlugRelatedField(slug_field='email', read_only=True)

  class Meta(StudentQuizAttemptSerializer.Meta):
    fields = StudentQuizAttemptSerializer.Meta.fields + ('student',)
