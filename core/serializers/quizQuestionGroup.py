# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import QuizQuestionGroup


class QuizQuestionGroupSerializer(ModelSerializerWithPOSTCheck):
  """A random-draw group on a quiz: pick N questions from a bank, each worth P points."""

  class Meta:
    model = QuizQuestionGroup
    fields = ('id', 'quiz', 'bank', 'name', 'pickCount', 'pointsPerQuestion', 'sortKey')
    POST_permissions_fields = ('quiz',)

  def validate(self, data):
    data = super().validate(data)
    proposed = self.genProposedFields(data)
    quiz = proposed.get('quiz')
    bank = proposed.get('bank')
    # The drawn bank must belong to the same course as the quiz.
    if quiz is not None and bank is not None and bank.course_id != quiz.course_id:
      raise serializers.ValidationError("The bank must belong to the same course as the quiz.")
    if proposed.get('pickCount') is not None and proposed['pickCount'] < 1:
      raise serializers.ValidationError("pickCount must be at least 1.")
    # Re-authorize the destination course: a PATCH could point `quiz` at another course's
    # quiz (object permissions only checked the source quiz's course).
    self.assert_authoring_course(quiz.course if quiz is not None else None)
    return data
