from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.serializers.template import ModelSerializerWithPOSTCheck
from core.models import SubmissionHistory, User

import pytz

class SubmissionHistorySerializer(ModelSerializerWithPOSTCheck):
  student = serializers.SlugRelatedField(many=False, slug_field='email', queryset=User.objects.all(), required=True)
  dateViewed = serializers.SerializerMethodField()

  class Meta:
    model = SubmissionHistory
    fields = ('id', 'student', 'submission', 'hasViewed','dateViewed')
    read_only_fields = ('student','submission','dateViewed')

  @extend_schema_field(serializers.DateTimeField(allow_null=True))
  def get_dateViewed(self, obj):
    if(obj.dateViewed):
      tz = pytz.timezone(obj.submission.assignment.course.timezone)
      return obj.dateViewed.astimezone(tz)
    else:
      return None
