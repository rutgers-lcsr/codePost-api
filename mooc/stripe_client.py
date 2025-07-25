import stripe
import os

from core.logging import logEvent
from util.slack import Slack
from django.conf import settings



class StripeClient:

  def __init__(self):
    raise NotImplementedError("This class is not meant to be instantiated directly. IN process of removing it from the codebase.")

    if 'ON_AWS' in os.environ:
      stripe.api_key = os.environ.get('STRIPE_API_KEY')
    else:
      stripe.api_key = 'sk_test_VSQyvppBKHsC8txe7mLvqDWk'
    # self.slack_client = Slack()
    self.sc = stripe

  def get_customer_by_email(self, email):
    customers = self.sc.Customer.list(email=email)
    if len(customers) > 1:
      logEvent("Stripe ERROR: Multiple Stripe Customers under same email",
               message=f"Multiple Stripe Customers found for email {email}" )
      # self.slack_client.send_message('Stripe ERROR: Multiple Stripe Customers under same email | {}'.format(
      #     user.email), channel="richard-test-2")
      raise ValueError("FIXME: Something went wrong; respond to client rather than fatal error")
    elif len(customers) == 1:
      return customers.data[0].id
    else:
      return None

  def create_customer(self, user):
    metadata = {
        "codepost_user_id": user.id,
    }
    return self.sc.Customer.create(email=user.email, metadata=metadata)

  def get_or_create_customer_id(self, user):
    codepost_customer_id = user.profile.stripeCustomerId
    stripe_customer_id = self.get_customer_by_email(user.email)

    # When testing locally, just take the Stripe ID as truth
    # Useful in the case of restarting DB
    if settings.DEBUG and stripe_customer_id:
      customer_id = stripe_customer_id
    else:
      # In production, stripe_customer_id and codepost_customer_id should always be in sync
      if not stripe_customer_id:
        customer = self.create_customer(user)
        customer_id = customer.id

        user.profile.stripeCustomerId = customer_id
        user.profile.save()
      else:
        if stripe_customer_id != codepost_customer_id:
          logEvent("Stripe ERROR: codePost and Stripe customer records dont match",
                   message=f"codePost customer ID {codepost_customer_id} does not match Stripe customer ID {stripe_customer_id} for user {user.email}")
          raise ValueError("FIXME: Something went wrong; respond to client rather than fatal error")

        customer_id = stripe_customer_id

    return customer_id

  def create_checkout_session(self, order, success_url='https://mooc.codepost.io', cancel_url='https://mooc.codepost.io'):
    line_items = [
        {
            "name": order.product.name,
            "description": order.description,
            "images": ['https://images-na.ssl-images-amazon.com/images/I/41%2BpJNrGujL._SX359_BO1,204,203,200_.jpg'],
            "amount": int(order.price),
            "currency": "usd",
            "quantity": 1,
        }
    ]

    # FIXME: update success / cancel urls
    session = self.sc.checkout.Session.create(
        customer=order.userStripeCustomerIdBackup,
        payment_method_types=['card'],
        line_items=line_items,
        payment_intent_data={
            "metadata": {
                "order": order.id,
                "assignments": str(list(order.assignments.all()))
            }
        },
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return session

  def retrieve_checkout_session(self, session_id):
    return self.sc.checkout.Session.retrieve(session_id)

  def retrieve_payment_intent(self, payment_intent_id):
    return self.sc.PaymentIntent.retrieve(payment_intent_id)
