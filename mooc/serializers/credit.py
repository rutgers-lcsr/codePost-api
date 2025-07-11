from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck

from core.models import User, Assignment
from mooc.models import Credit


class CreditSerializer(ModelSerializerWithPOSTCheck):

  class Meta:
    model = Credit
    fields = ('id', 'submission', 'rating', 'assignment')