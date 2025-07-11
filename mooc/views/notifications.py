from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from mooc.stripe_client import StripeClient
from util.slack import Slack
import os

from core.emails import send_email_sendgrid, get_email_template_id, get_email_params

# These are the test secrets. Live secret is in AWS environs
ngrok_endpoint_secret = "whsec_AzEkG7bOurzh1F9R7VKVSj7pajI9DdmU"
test_endpoint_secret = "whsec_XhfxEFDFZflYQIc8CiPFXzNBE00XQb8Z"


@api_view(['POST'])
def notification_webhook(request):
    sc = StripeClient().sc

    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    event = None

    if 'ON_AWS' in os.environ:
        endpoint_secret = os.environ.get('STRIPE_NOTIFICATION_WEBHOOK_SECRET')
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

    # Whenever a payment_intent transitions to canceled, send a follow up email
    # Usually this happens ~24 hours after a Checkout Session is created and not
    # completed.
    if event['type'] == 'payment_intent.canceled':
        if event['data']['object']['customer'] != None:
            try:
                user = sc.Customer.retrieve(event['data']['object']['customer'])
                send_email_sendgrid(from_email="help@codepost.io", to_email=user['email'], params=get_email_params(
                    'MOOC_FOLLOW_UP', {}), templateID=get_email_template_id('MOOC_FOLLOW_UP'))
            except Exception as e:
                slack_client = Slack()
                slack_client.send_message('Stripe ERROR: Failed follow up email | {}'.format(
                    e), channel="#stripe", logInDebug=True, debugChannel="#richard-test")

    return Response('success', status.HTTP_200_OK)
