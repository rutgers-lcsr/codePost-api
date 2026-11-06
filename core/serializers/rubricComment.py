# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import RubricComment

from haikunator import Haikunator

###############################################################
# Utility functions
###############################################################
def generate_random_name():
    """
    Generate a Heroku-style random name
    """
    haikunator = Haikunator()

    # format: token-adjective-noun
    els = haikunator.haikunate().split('-')
    return '-'.join([els[2], els[0], els[1]])

###############################################################

class RubricCommentSerializer(ModelSerializerWithPOSTCheck):
  isApplied = serializers.SerializerMethodField()

  class Meta:
    model = RubricComment
    fields = ('id', 'text', 'pointDelta', 'category', 'sortKey', 'explanation', 'instructionText', 'templateTextOn', 'name', 'isApplied')
    read_only_fields = ('isApplied',)
    POST_permissions_fields = ('category',)
    extra_kwargs = {"text": {"trim_whitespace": False}, "explanation": {
        "trim_whitespace": False}, "instructionText": {"trim_whitespace": False}}

  @extend_schema_field(serializers.BooleanField())
  def get_isApplied(self, obj):
    """True once any grading Comment uses this rubric comment. Listings annotate
    `applied` so this costs no per-comment query; a parent that only nests comments
    which use the rubric comment sets `rubric_comments_applied`."""
    if getattr(self.parent, 'rubric_comments_applied', False):
      return True
    applied = getattr(obj, 'applied', None)
    return obj.comments.exists() if applied is None else applied

  def validate(self, data):
    newData = super().validate(data)
    proposedFields = self.genProposedFields(newData)

    # rubric comment needs a name
    if proposedFields.get('name', None) is None:
      newData['name'] = generate_random_name()

    # client is trying to set a new name
    if 'name' in newData and newData['name'] is not None:
        same_name_set = RubricComment.objects.filter(name=newData['name'], category__assignment=proposedFields['category'].assignment)
        conflicts = same_name_set
        if self.instance:
            conflicts = list(filter(lambda x: x.id != self.instance.id, same_name_set))  # type: ignore[union-attr]  # instance set during update

        if len(conflicts) > 0:
            raise serializers.ValidationError("Name is already used by another rubric comment within this assignment.")

    return newData