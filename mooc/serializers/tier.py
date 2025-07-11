from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck

from core.models import Course
from mooc.models import Tier

from core.serializers.course import MoocCourseSerializer


class TierSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = Tier
    fields = ('id', 'product', 'name', 'description', 'rateTotal')
