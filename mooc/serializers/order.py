from rest_framework import serializers
from core.serializers.template import ModelSerializerWithPOSTCheck
from django.core.exceptions import ObjectDoesNotExist
from django.utils.encoding import force_str

from core.models import User, Assignment, Organization
from mooc.models import Order, Credit

from core.views.registration import send_email_to_joining_user_mooc


class CreatableSlugRelatedField(serializers.SlugRelatedField):

  def to_internal_value(self, data):
    fields = {self.slug_field: data}

    # Handle User get_or_create
    if self.slug_field == 'email':
      fields = {self.slug_field: data, 'username': data}

    try:
      ret = self.get_queryset().get_or_create(**fields)
      user = ret[0]

      # If this is a new user, set their Organization
      if ret[1]:
        user.is_active = False
        organization = Organization.objects.get(name="mooc")
        user.profile.organization = organization
        user.save()

        # Send join email
        send_email_to_joining_user_mooc(user)

      return user

    except ObjectDoesNotExist:
      self.fail('does_not_exist', slug_name=self.slug_field, value=force_str(data))
    except (TypeError, ValueError):
      self.fail('invalid')


class OrderPostSerializer(ModelSerializerWithPOSTCheck):
  user = CreatableSlugRelatedField(
      many=False, slug_field='email', queryset=User.objects.all(), required=True)

  class Meta:
    model = Order
    fields = ('id', 'user', 'product', 'assignments', 'tier')

  def validate(self, data):
    new_data = super().validate(data)
    user = new_data['user']
    assignments = new_data['assignments']
    product = new_data['product']
    tier = new_data['tier']

    for assignment in assignments:
      if assignment.course != product.course:
        raise serializers.ValidationError("Assignments must belong to the product course.")

      credits = Credit.objects.filter(user=user, assignment=assignment)
      if credits.count() > 0:
        raise serializers.ValidationError("The order contains already purchased assignments.")


    if tier.product_id != product.id:
      raise serializers.ValidationError("Invalid tier.")

    if len(assignments) > 1:
      all_assignments = product.course.assignments.all()
      purchased_assignments = Credit.objects.filter(user=user, assignment__in=all_assignments).all()
      expected_bundle = set(all_assignments) - set(purchased_assignments)

      if set(expected_bundle) != set(assignments):
        raise serializers.ValidationError("Invalid bundle.")

    return new_data


class OrderReadSerializer(ModelSerializerWithPOSTCheck):
  user = serializers.SlugRelatedField(many=False, slug_field='email', queryset=User.objects.all(), required=True)

  class Meta:
    model = Order
    fields = ('id', 'user', 'product', 'assignments', 'stripeSessionId',
              'userStripeCustomerIdBackup', 'baseRate', 'discountRate', 'tier', 'rateTotal')
