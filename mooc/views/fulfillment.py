import os
import logging

logger = logging.getLogger("django")

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from mooc.stripe_client import StripeClient
from util.slack import Slack

# These are the test secrets. Live secret is in AWS environ
ngrok_endpoint_secret = "whsec_xsaqn8yfgodBXjOBxJ7SV8wRmTA2Ixf0"
test_endpoint_secret = "whsec_ktF6BvG4s959UfOQS6T5pjveMcwclkI9"


@api_view(['POST'])
def fulfillment_webhook(request):
  slack_client = Slack()
  sc = StripeClient().sc

  payload = request.body
  sig_header = request.META['HTTP_STRIPE_SIGNATURE']
  event = None

  if 'ON_AWS' in os.environ:
    endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
  else:
    endpoint_secret = ngrok_endpoint_secret

  try:
    event = sc.Webhook.construct_event(
        payload, sig_header, endpoint_secret
    )
  except ValueError as e:
    # Invalid payload
    return Response(e, status.HTTP_400_BAD_REQUEST)
  except sc.error.SignatureVerificationError as e:
    # Invalid signature
    return Response(e, status.HTTP_400_BAD_REQUEST)

  # Handle the checkout.session.completed event
  if event['type'] == 'checkout.session.completed':
    session = event['data']['object']

    slack_client.send_message('💲💲 Completed Payment!', channel="richard-test-2")

    # payment_intent = sc.PaymentIntent.retrieve(session.payment_intent)

    # if 'order' in payment_intent.metadata:
    #   order = Order.objects.get(id=int(payment_intent.metadata['order']))
    #   order.complete()
    #   order.save()

    #   user = order.user
    #   course = order.product.course

    #   if not course.students.filter(email=user.email):
    #     course.students.add(user)
    #     course.save()

    #   slack_client.send_message('💲💲 ({}) Completed Payment! Order [{}] | Assignments [{}]'.format(order.price,
    #                                                                                               payment_intent.metadata['order'], payment_intent.metadata['assignments']), channel="richard-test-2")

  else:
      logger.error(f"Unhandled event type: {event['type']}")
      # slack_client.send_message('Stripe ERROR: Session completed without order metadata | session [{}]'.format(
          # session.id), channel="richard-test-2")

  return Response('fulfilled', status.HTTP_200_OK)
