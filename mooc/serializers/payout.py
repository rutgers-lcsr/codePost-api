import pytz
from datetime import timezone

from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck

from core.models import User
from mooc.models import Payout, Review


class PayoutPostSerializer(ModelSerializerWithPOSTCheck):
  reviewer = serializers.SlugRelatedField(many=False, slug_field='email', queryset=User.objects.all(), required=False)

  class Meta:
    model = Payout
    fields = ('id', 'reviewer',)


class PayoutSerializer(ModelSerializerWithPOSTCheck):
  completedAt = serializers.SerializerMethodField()
  created = serializers.SerializerMethodField()

  class Meta:
    model = Payout
    fields = ('id', 'reviewer', 'status', 'created', 'completedAt', 'amount')

  def get_completedAt(self, obj):
    if obj.completedAt:
      tz = pytz.timezone('America/New_York')
      return obj.completedAt.astimezone(tz)
    else:
      return ''

  def get_created(self, obj):
    tz = pytz.timezone('America/New_York')
    return obj.created.astimezone(tz)
