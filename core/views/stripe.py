import datetime
import os
import urllib.parse

import pytz
import stripe
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Course
from core.permissions.permissions import BillingPermissions
from core.serializers.course import CourseSerializer

stripe.api_key = os.environ.get("STRIPE_API_KEY", default="sk_test_VSQyvppBKHsC8txe7mLvqDWk")

STANDARD_CORE_PRICE_PER_STUDENT_CENTS = 100
STANDARD_PRO_PRICE_PER_STUDENT_CENTS = 400


def get_payment_details(course):
    stripe_payment_intents = stripe.PaymentIntent.search(
        query=f"metadata['course']:'{course.id}'"
    )["data"]

    tz = pytz.timezone(course.timezone)

    # from the array of dictionaries, only keep specific fields
    stripe_payment_intents_compressed = []
    for payment_intent in stripe_payment_intents:
        x = {
            "id": payment_intent["id"],
            "status": payment_intent["status"],
            "timestamp": payment_intent["created"],
            "created": datetime.datetime.utcfromtimestamp(payment_intent["created"])
            .astimezone(tz)
            .strftime("%Y-%m-%d %H:%M:%S %Z"),
            "amount": payment_intent["amount"],
            "currency": payment_intent["currency"],
            "description": payment_intent["description"],
            "receipt_email": payment_intent["receipt_email"],
            "manual": False,
        }
        stripe_payment_intents_compressed.append(x)

    manual_payments = course.manual_payments

    for payment in manual_payments:
        x = {
            "id": payment.id,
            "status": "succeeded",
            "timestamp": payment.timestamp,
            "created": payment.timestamp.astimezone(tz).strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            ),
            "amount": payment.amount,
            "currency": "usd",
            "description": payment.description,
            "receipt_email": payment.email,
            "manual": True,
        }
        stripe_payment_intents_compressed.append(x)

    stripe_payment_intents_compressed = sorted(
        stripe_payment_intents_compressed,
        key=lambda x: x["timestamp"],
        reverse=True,
    )

    total_paid_cents = sum(
        [
            payment_intent["amount"]
            for payment_intent in stripe_payment_intents_compressed
            if payment_intent["status"] == "succeeded"
        ]
    )

    total_active_students = course.students.count()
    expected_paid_core = total_active_students * STANDARD_CORE_PRICE_PER_STUDENT_CENTS
    expected_paid_autograder = (
        total_active_students * STANDARD_PRO_PRICE_PER_STUDENT_CENTS
    )

    show_banner = False
    if course.waiver_requested:
        show_banner = False
    elif total_active_students > 0 and not (
        total_paid_cents == expected_paid_core
        or total_paid_cents == expected_paid_autograder
    ):
        show_banner = True

    show_payment_buttons = True
    if total_active_students > 0 and total_paid_cents == expected_paid_autograder:
        show_payment_buttons = False

    response = {
        "payment_intents": stripe_payment_intents_compressed,
        "total_paid_cents": total_paid_cents,
        "total_active_students": total_active_students,
        "show_banner": show_banner,
        "show_payment_buttons": show_payment_buttons,
        "waiver_requested": course.waiver_requested,
    }

    return response


class BillingViewSet(viewsets.ModelViewSet):  # noqa: F821
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = (IsAuthenticated, BillingPermissions)

    @action(detail=True, methods=["GET"])
    def details(self, request, pk=None):
        user = request.user
        course = self.get_object()

        if course not in user.courseAdmin_courses.all():
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        response = get_payment_details(course)

        return Response(response, status=status.HTTP_200_OK)

    @action(detail=True, methods=["GET"])
    def request_waiver(self, request, pk=None):
        user = request.user
        course = self.get_object()

        if course not in user.courseAdmin_courses.all():
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        course.waiver_requested = True
        course.save()

        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=["POST"])
    def create_checkout_session(self, request, pk=None):
        """
        No billing profile yet
        """
        if "localhost" in request.build_absolute_uri():
            domain_url = "http://localhost:3000"
        else:
            domain_url = "https://codepost.io"

        user = request.user
        course = self.get_object()

        if course not in user.courseAdmin_courses.all():
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        base_url = f"{domain_url}/admin/{urllib.parse.quote(course.name)}/{urllib.parse.quote(course.period)}/billing"

        details = get_payment_details(course)

        plan_type = request.data.get("plan_type", "core")
        if plan_type not in ["core", "pro"]:
            return Response(
                {"error": {"message": "Invalid plan type."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        price = (
            STANDARD_CORE_PRICE_PER_STUDENT_CENTS
            if plan_type == "core"
            else STANDARD_PRO_PRICE_PER_STUDENT_CENTS
        )

        amount = details["total_active_students"] * price - details["total_paid_cents"]

        if amount <= 0:
            return Response(
                {"error": {"message": "No payment required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Create new Checkout Session for the order
            # Other optional params include:
            # [billing_address_collection] - to display billing address details on the page
            # [customer] - if you have an existing Stripe Customer ID
            # [customer_email] - lets you prefill the email input in the form
            # For full details see https:#stripe.com/docs/api/checkout/sessions/create

            # ?session_id={CHECKOUT_SESSION_ID} means the redirect will have the session ID set as a query param
            students = details["total_active_students"]
            checkout_session = stripe.checkout.Session.create(
                success_url=base_url + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=base_url + "?session_id=cancel",
                customer_email=user.email,
                mode="payment",
                line_items=[
                    {
                        "quantity": 1,
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": amount,
                            "product_data": {
                                "name": f"{course.name} ({course.period}): {students} students ({plan_type} plan)"
                            },
                        },
                    }
                ],
                payment_intent_data={
                    "description": f"{course.name} | {course.period}",
                    "metadata": {
                        "course": course.id,
                        "customer": user.email,
                        "students": students,
                        "plan_type": plan_type,
                    },
                },
                metadata={
                    "course": course.id,
                },
            )

            return Response(
                {"sessionId": checkout_session["id"], "url": checkout_session["url"]},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": {"message": str(e)}}, status=status.HTTP_400_BAD_REQUEST
            )
