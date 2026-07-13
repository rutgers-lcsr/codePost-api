# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import CommentTemplate
from core.permissions.helpers import isCourseStaff

class CommentTemplateSerializer(ModelSerializerWithPOSTCheck):
    owner = serializers.SlugRelatedField(many=False, slug_field='email', read_only=True)
    
    class Meta:
        model = CommentTemplate
        fields = ('id', 'text', 'owner', 'assignment', 'isGlobal', 'filePath', 'pointDelta', 'rubricComment', 'sourceComment', 'cellId')
        read_only_fields = ('id', 'owner')
        POST_permissions_fields = ('assignment',)

    def validate(self, data):
        if self.instance is None:
            if 'owner' not in data:
                data['owner'] = self.context['request'].user
        
        assignment = data.get('assignment')
        if not assignment and self.instance:
            assignment = self.instance.assignment
            
        if assignment:
            user = data.get('owner', self.context['request'].user)
            course = assignment.course
            if not isCourseStaff(user, course):
                raise serializers.ValidationError("User is not staff of this course.")

            # Super Grader check for isGlobal
            if data.get('isGlobal', False):
                is_super = course.superGraders.filter(pk=user.pk).exists() or course.courseAdmins.filter(pk=user.pk).exists()
                if not is_super:
                    raise serializers.ValidationError("Only Super Graders or Admins can create global templates.")
        
        return super().validate(data)

