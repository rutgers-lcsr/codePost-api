from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Comment, User, CommentTag
from core.permissions.helpers import isCourseStaff
import re
import json

from core.validators import validate_hex_color


class CommentSerializer(ModelSerializerWithPOSTCheck):
  author = serializers.SlugRelatedField(many=False, slug_field='email', queryset=User.objects.all(), required=False)
  color = serializers.SerializerMethodField()
  tags = serializers.SlugRelatedField(many=True, slug_field='label',
                                      queryset=CommentTag.objects.all(), allow_null=True, required=False)

  class Meta:
    model = Comment
    fields = ('id', 'text', 'pointDelta', 'startChar', 'endChar', 'startLine',
              'endLine', 'file', 'rubricComment', 'author', 'feedback', 'color', 'tags')
    read_only_fields = ('feedback',)
    POST_permissions_fields = ('file',)
    extra_kwargs = {'endLine': {'required': False}, 'startChar': {'required': False}, 'endChar': {'required': False}, "text": {"trim_whitespace": False}}

  def get_color(self, obj):
    return getattr(obj, 'color', None)

  def validate_startChar(self, data):
    if data < 0:
      raise serializers.ValidationError("startChar cannot be less than 0")
    return data

  def validate_endChar(self, data):
    if data < 0:
      raise serializers.ValidationError("startChar cannot be less than 0")
    return data

  def validate_startLine(self, data):
    if data < 0:
      raise serializers.ValidationError("startLine cannot be less than 0")
    return data

  def validate_endLine(self, data):
    if data < 0:
      raise serializers.ValidationError("endLine cannot be less than 0")
    return data

  def validate(self, data):
    # Set smart comment defaults, but only if the comment is being created.
    if self.instance is None:
      data['endLine'] = data.get('endLine', data['startLine'])
      data['startChar'] = data.get('startChar', 0)

      try:
        fallback = len(data['file'].data.split('\n')[data['endLine']])
      except:
        fallback = 0

      # Default to the last character of endLine
      data['endChar'] = data.get('endChar', fallback)

    if 'author' not in data:
      data['author'] = self.context['request'].user

    newData = super().validate(data)
    proposedFields = self.genProposedFields(newData)

    # Consider adding a check to disallow non-admins from editing the authors of comments
    # We would need to raise a permissions error, not a validation error.
    proposedCourse = proposedFields['file'].submission.assignment.course
    if not isCourseStaff(proposedFields['author'], proposedCourse):
      raise serializers.ValidationError("Author must be a grader or admin of course.")

    if proposedFields['endLine'] == proposedFields['startLine'] and proposedFields['endChar'] < proposedFields['startChar']:
      raise serializers.ValidationError("endChar cannot be < startChar on the same line")

    if proposedFields['endLine'] < proposedFields['startLine']:
      raise serializers.ValidationError("endLine cannot be < startLine")

    # Check that endLine does not exceed the number of lines in the file
    if proposedFields['file'] and proposedFields['file'].extension != 'pdf':

      if proposedFields['file'].extension in ['ipynb', '.ipynb']:
        # FIXME: To dynamically calculate the number of cells in a Jupyter Notebook, we need to do two things:
        # 1) len(json.loads(proposedFields['file'].data['cells']))
        # 2) Calc array length of all cell types (e.g. Markdown, Output, Code)
        #
        # Hardcoding the number of cells makes the API vulnerable to saving invalid comments (beyond the length scope of the file)
        numMatches = 20000
      else:
        numMatches = len(re.findall("\n", proposedFields['file'].data)) + 1
      if proposedFields['endLine'] > numMatches:
        raise serializers.ValidationError("endLine exceeds the lines in the specified file's data")

    if 'color' in proposedFields and proposedFields['color'] is not None:
      if proposedFields['color'] != '':
        try:
          validate_hex_color(proposedFields['color'])
        except:
          raise serializers.ValidationError("color must be a valid hexadecimal color value")

    # Check that rubricComment and file belong to the same assignment
    # if 'rubricComment' in newData:
    #   rubricComment = newData['rubricComment']
    #   if rubricComment.category.assignment != file.submission.assignment:
    #     raise serializers.ValidationError("File and rubricComment must belong to the same assignment.")

    return newData


class CommentBasicSerializer(serializers.ModelSerializer):
  tags = serializers.SlugRelatedField(many=True, slug_field='label', queryset=CommentTag.objects.all(), allow_null=True)

  class Meta:
    model = Comment
    fields = ('id', 'text', 'pointDelta', 'startChar', 'endChar',
              'startLine', 'endLine', 'file', 'rubricComment', 'feedback', 'tags')
    read_only_fields = ('id', 'text', 'pointDelta', 'startChar', 'endChar',
                        'startLine', 'endLine', 'file', 'rubricComment', 'feedback')
    extra_kwargs = {"text": {"trim_whitespace": False}}
