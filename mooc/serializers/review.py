from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck

from core.models import User, Assignment
from mooc.models import Review


class ReviewSerializer(ModelSerializerWithPOSTCheck):
  reviewer = serializers.SlugRelatedField(many=False, slug_field='email',
                                          queryset=User.objects.all(), required=False, allow_null=True)
  submissionID = serializers.IntegerField(source='credit.submission.id')
  assignmentName = serializers.CharField(source='credit.assignment.name')

  class Meta:
    model = Review
    fields = ('credit', 'reviewer', 'submissionID', 'assignmentName', 'rateReview', 'status', 'payout')
