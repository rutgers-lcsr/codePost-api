# NOTES:
# This module was updated to use `viewflow.fsm` instead of `django_fsm`.
# The `fsm` decorator is now used for state transitions.
# Still needs a check if this migration worked correctly, django‐fsm to viewflow.fsm
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.timezone import now
from django.core.exceptions import ValidationError
from django.dispatch import receiver
from django.db.models.signals import pre_save

from core.models import Course, Assignment, User, Profile, Submission
from django.conf import settings
from viewflow.fsm import Transition

from mooc.stripe_client import StripeClient


class BaseModel(models.Model):
  created = models.DateTimeField(editable=False, default=now)
  modified = models.DateTimeField(default=now)

  class Meta:
    abstract = True

  def save(self, *args, **kwargs):
    ''' On save update timestamps '''
    primary_key = self._meta.pk.name

    if not getattr(self, primary_key):
      self.created = now()
    self.modified = now()
    self.full_clean()
    return super(BaseModel, self).save(*args, **kwargs)


class Product(BaseModel):
  name = models.TextField(default='')
  course = models.ForeignKey(Course, on_delete=models.SET_NULL, blank=True, null=True)
  url = models.TextField(default='', blank=True)
  offeredBy = models.TextField(default='', blank=True)


  # Deprecated
  cBaseRate = models.IntegerField(default=0)
  # Deprecated
  cDiscountRate = models.DecimalField(max_digits=4, decimal_places=2,
                                      validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
                                      )
  # Deprecated
  cReviewRate = models.IntegerField(default=0)

  def __str__(self):
    return "{name} | {period} ({id})".format(name=self.course.name, period=self.course.period, id=self.id)

class Tier(BaseModel):
  product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="tiers")
  name = models.TextField(default='Basic Tier', blank=True)
  description = models.TextField(default='')
  rateTotal = models.IntegerField(default=0, help_text="Total (cents)")
  rateReview = models.IntegerField(default=0, help_text="Rate paid to reviewer (cents)")

  def clean(self):
      """ Validation for tiers. """
      if self.rateReview > self.rateTotal:
          raise ValidationError(
              "Rate must be greater than reviewRate."
          )

  def __str__(self):
    return "{name} ({product})".format(name=self.name, product=str(self.product))

class Order(BaseModel):
  userStripeCustomerIdBackup = models.TextField(default='', blank=True)
  stripeSessionId = models.TextField(default='', blank=True)

  user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)

  # FIXME: Product is really "through" Tier now. Keeping Product field to not break stuff
  product = models.ForeignKey(Product, on_delete=models.PROTECT)
  tier = models.ForeignKey(Tier, on_delete=models.PROTECT, null=True)

  assignments = models.ManyToManyField(Assignment, related_name="assignment_orders")

  rateTotal = models.IntegerField(default=0, help_text="Total (cents)")
  rateReview = models.IntegerField(default=0, help_text="Rate paid to reviewer (cents)")


  status = models.CharField(default='created', max_length=20)

  # Deprecated
  baseRate = models.IntegerField(default=0)
  # Deprecated
  discountRate = models.DecimalField(max_digits=4, decimal_places=2,
                                     validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
                                     )
  # Deprecated
  reviewRate = models.IntegerField(default=0)

  def __str__(self):
    return "{user} | {status} ({id})".format(user=self.user.email if self.user else 'No user', status=self.status, id=self.id)



  @property
  def price(self):
    return self.rateTotal

  @property
  def margin(self):
    return self.rateTotal - self.rateReview

  @property
  def description(self):
    return "Good for one {tier_name}code review credit. After checking out, you'll be able to submit your code for review!".format(tier_name="{} ".format(self.tier.name) if self.tier else "")

  def can_complete(self):
    if self.userStripeCustomerIdBackup == '' or self.assignments.count() == 0 or self.stripeSessionId == None:
      return False

    session = StripeClient().retrieve_checkout_session(self.stripeSessionId)
    payment_intent = StripeClient().retrieve_payment_intent(session.payment_intent)
    if payment_intent.status == 'succeeded' or settings.DEBUG:
      return True
    else:
      return False
  # Still need a check if this migration worked correctly, django‐fsm to viewflow.fsm
  # @Transition(label=status, source='created', target='paid', conditions=[can_complete])
  def complete(self):
    """
    For each assignment, create a (Credit, Review) pair
    """
    session = StripeClient().retrieve_checkout_session(self.stripeSessionId)

    for assignment in self.assignments.all():
      credit = Credit.objects.create(stripePaymentIntentId=session.payment_intent,
                                     user=self.user, assignment=assignment, order=self)
      review = Review.objects.create(credit=credit)

  def clean_fields(self, exclude=None):
    super(Order, self).clean_fields(['status'])

  def clean(self):
    # Put more model-level validations here
    # Discussion whether to keep them
    # in the Serializer, here, or both
    pass


class Payout(BaseModel):
  completedAt = models.DateTimeField(null=True, blank=True)
  reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
  status = models.CharField(default='pending',max_length=20)

  @property
  def amount(self):
    total = 0

    for review in self.reviews.all():
      total += review.reviewRate

    return total

  def can_complete(self):
    for review in self.reviews.all():
      if not review.approved:
        return False

      if not review.reviewer == self.reviewer:
        return False

    if self.amount < 0:
      return False

    # Failsave :-)
    if self.amount > 20000:
      return False

    return True

  # @Transition(label=status, source='pending', target='paid', conditions=[can_complete])
  def complete(self):
    self.completedAt = now()
    self.save()


class Credit(BaseModel):
  """
  Always created by Order.complete
  """
  stripePaymentIntentId = models.TextField(default='')
  user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
  assignment = models.ForeignKey(Assignment, related_name="credits", on_delete=models.SET_NULL, blank=True, null=True)
  order = models.ForeignKey(Order, on_delete=models.PROTECT)

  submission = models.OneToOneField(Submission, on_delete=models.SET_NULL, blank=True, null=True)

  rating = models.IntegerField(default=0)

  @property
  def tier(self):
    return self.order.tier

  def __str__(self):
    return "{user} ({tier}) ({id})".format(user=self.user.email, tier=str(self.order.tier), id=self.id)

  # FIXME
  # https://stackoverflow.com/questions/33307892/django-unique-together-with-nullable-foreignkey
  # class Meta:
  #   unique_together = ('user', 'assignment')


class Review(BaseModel):
  """
  Always created by Order.complete
  """
  credit = models.OneToOneField(Credit, on_delete=models.PROTECT, primary_key=True)
  reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)

  approved = models.BooleanField(default=False)
  approvedAt = models.DateTimeField(null=True, blank=True)

  payout = models.ForeignKey(Payout, on_delete=models.SET_NULL, blank=True, null=True, related_name="reviews",)

  @property
  def rateReview(self):
    return self.credit.order.rateReview

  @property
  def status(self):
    if not self.credit.submission.isFinalized:
      return 'not finalized'
    elif not self.approved:
      return 'pending approval'
    elif not self.payout:
      return 'approved'
    elif self.payout and self.payout.status == 'pending':
      return 'requested payout'
    elif self.payout and self.payout.status == 'paid':
      return 'paid'
    else:
      return ''

  class Meta:
    unique_together = ('credit', 'reviewer')


############# Signals #########################################################


@receiver(pre_save, sender=Review)
def set_approved_at(sender, instance, **kwargs):
  try:
    obj = sender.objects.get(pk=instance.pk)
  except sender.DoesNotExist:
    pass
  else:
    if not obj.approved and instance.approved:  # Review has been approved
      instance.approvedAt = now()
    elif obj.approved and not instance.approved:
      instance.approvedAt = None
