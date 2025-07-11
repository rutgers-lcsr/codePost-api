from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck

from core.models import Course
from mooc.models import Product

from core.serializers.course import MoocCourseSerializer
from mooc.serializers.tier import TierSerializer


class ProductSerializer(ModelSerializerWithPOSTCheck):
  course = MoocCourseSerializer(many=False)
  tiers = TierSerializer(many=True)

  class Meta:
    model = Product
    fields = ('id', 'name', 'course', 'url', 'offeredBy', 'cBaseRate', 'cDiscountRate', 'tiers')
