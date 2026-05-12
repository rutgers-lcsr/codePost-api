# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import Section, User
from core.permissions.helpers import isGrader, isStudent, should_use_student_captions

class SectionSerializer(ModelSerializerWithPOSTCheck):
  leaders = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)
  students = serializers.SlugRelatedField(many=True, slug_field='email', queryset=User.objects.all(), allow_null=True)

  class Meta:
    model = Section
    fields = ('name', 'id', 'course', 'leaders', 'students')
    POST_permissions_fields = ('course',)

  def to_representation(self, obj):
    ret = super().to_representation(obj)
    course = obj.course

    if 'request' in self.context and should_use_student_captions(self.context['request'].user, course):
        caption_map = obj.course.studentCaptions
        ret['students'] = list(map(lambda x: caption_map[x.email] if x.email in caption_map else x.email, obj.students.all()))
    return ret

  def validate(self, data):
    newData = super().validate(data)
    newFields = self.genProposedFields(newData)

    if 'leaders' in newData:
      for grader in newData['leaders']:
        if not isGrader(grader, newFields['course']): # can't add grader who is not in the course.
          raise serializers.ValidationError("The following grader is not a member of the specified course: " + grader.email)

    if 'students' in newData:
      for student in newData['students']:
        if not isStudent(student, newFields['course']): # can't add student who is not in the course.
          raise serializers.ValidationError("The following student is not a member of the specified course: " + student.email)

    # remove students from all other sections of this course
    for student in newData['students']:
        other_sections = newData['course'].sections.filter(students__in=[student])
        for section in other_sections:
            section.students.remove(student)

    return newData
