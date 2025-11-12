from decimal import Decimal
import json

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

import stripe

from courses.models import Course, Enrollment
from courses.serializers import DynamicFieldSerializer
from courses.services.enrollment_service import enroll_user_in_course
from .models import Payment


def _get_success_cancel_urls() -> tuple[str, str]:
    base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000")
    success_path = getattr(settings, "STRIPE_SUCCESS_PATH", "/payment/success")
    cancel_path = getattr(settings, "STRIPE_CANCEL_PATH", "/payment/cancel")
    success_url = f"{base}{success_path}?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base}{cancel_path}"
    return success_url, cancel_url


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_checkout_session_view(request, course_id):
    """
    Create a Stripe Checkout Session for a paid course.
    For free courses, enroll immediately.
    """
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)

    # Free course: enroll immediately
    if course.price == 0 or Decimal(course.price) == Decimal("0.00"):
        success, message = enroll_user_in_course(request.user, course)
        if not success:
            return Response({"success": False, "message": message}, status=status.HTTP_400_BAD_REQUEST)
        enrollment = Enrollment.objects.get(student=request.user, course=course)
        ser = DynamicFieldSerializer(enrollment, model_name="enrollment", context={"request": request})
        return Response({"success": True, "message": "Enrolled successfully.", "data": ser.data}, status=status.HTTP_201_CREATED)

    # Paid course: ensure pending enrollment exists
    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
        defaults={"progress": 0.0, "payment_status": "pending", "is_enrolled": False},
    )

    # Check if already paid
    if enrollment.payment_status == "completed":
        return Response({"success": False, "message": "Already enrolled in this course."}, status=status.HTTP_400_BAD_REQUEST)

    if not settings.STRIPE_SECRET_KEY:
        return Response({"success": False, "message": "Stripe is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Create payment record
    payment = Payment.objects.create(
        user=request.user,
        course=course,
        enrollment=enrollment,
        amount=course.price,
        currency="usd",
        status=Payment.STATUS_PENDING,
    )

    unit_amount = int(Decimal(course.price) * 100)
    success_url, cancel_url = _get_success_cancel_urls()

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": course.title, "description": (course.description or "")[:250]},
                "unit_amount": unit_amount,
            },
            "quantity": 1,
        }],
        customer_email=request.user.email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "payment_id": str(payment.id),
            "enrollment_id": str(enrollment.id),
            "course_id": str(course.id),
            "user_id": str(request.user.id),
        },
    )

    payment.stripe_checkout_session_id = session.get("id", "")
    if session.get("payment_intent"):
        payment.stripe_payment_intent_id = str(session["payment_intent"])
    payment.save(update_fields=["stripe_checkout_session_id", "stripe_payment_intent_id", "updated_at"])

    return Response({
        "success": True,
        "message": "Checkout session created.",
        "data": {
            "checkout_session_id": session.get("id"),
            "checkout_url": session.get("url"),
            "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        },
    }, status=status.HTTP_201_CREATED)


def _finalize_from_checkout_session(session) -> tuple[bool, str, dict]:
    """
    Finalize payment and enrollment records after Stripe checkout completion.
    """
    metadata = session.get("metadata", {}) or {}
    payment_id = metadata.get("payment_id")
    enrollment_id = metadata.get("enrollment_id")
    user_id = metadata.get("user_id")
    course_id = metadata.get("course_id")
    payment_intent_id = session.get("payment_intent", "")
    customer_id = session.get("customer", "")

    # Locate payment
    payment = None
    if payment_id:
        try:
            payment = Payment.objects.get(id=payment_id)
        except Payment.DoesNotExist:
            payment = None
    if not payment:
        payment = Payment.objects.filter(stripe_checkout_session_id=session.get("id", "")).first()
    if not payment and user_id and course_id:
        payment = Payment.objects.filter(user_id=int(user_id), course_id=int(course_id)).order_by("-created_at").first()

    if payment and payment.status != Payment.STATUS_SUCCEEDED:
        payment.mark_succeeded(payment_intent_id=payment_intent_id or "", customer_id=customer_id or "")

    # Activate enrollment
    enrollment = None
    if enrollment_id:
        try:
            enrollment = Enrollment.objects.get(id=enrollment_id)
            if enrollment.payment_status != "completed":
                enrollment.payment_status = "completed"
                enrollment.is_enrolled = True
                enrollment.save(update_fields=["payment_status", "is_enrolled", "updated_at"])
                enrollment.unlock_first_module()
                enrollment.calculate_progress()
        except Enrollment.DoesNotExist:
            enrollment = None

    if not enrollment and user_id and course_id:
        enrollment, _ = Enrollment.objects.get_or_create(
            student_id=int(user_id),
            course_id=int(course_id),
            defaults={"progress": 0.0, "payment_status": "completed", "is_enrolled": True},
        )
        if enrollment.payment_status != "completed":
            enrollment.payment_status = "completed"
            enrollment.is_enrolled = True
            enrollment.save(update_fields=["payment_status", "is_enrolled", "updated_at"])
        enrollment.unlock_first_module()
        enrollment.calculate_progress()

    context = {
        "enrollment_id": getattr(enrollment, "id", None),
        "payment_id": getattr(payment, "id", None),
        "payment_status": getattr(payment, "status", None),
        "enrollment_payment_status": getattr(enrollment, "payment_status", None),
        "is_enrolled": getattr(enrollment, "is_enrolled", None),
    }
    return True, "Payment confirmed and enrollment activated.", context


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def confirm_checkout_session_view(request, session_id=None):
    """
    Confirm a Stripe Checkout Session from the frontend success page.
    """
    sid = session_id or request.data.get("session_id") or request.query_params.get("session_id")
    if not sid:
        return Response({"success": False, "message": "session_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not settings.STRIPE_SECRET_KEY:
        return Response({"success": False, "message": "Stripe is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.retrieve(sid)
    except Exception:
        return Response({"success": False, "message": "Invalid or unknown session_id."}, status=status.HTTP_400_BAD_REQUEST)

    # Check payment status
    is_paid = str(session.get("payment_status", "")).lower() == "paid"
    if not is_paid and session.get("payment_intent"):
        pi = stripe.PaymentIntent.retrieve(session.get("payment_intent"))
        is_paid = str(pi.get("status", "")).lower() == "succeeded"

    if not is_paid:
        # Mark payment failed/canceled
        try:
            payment = Payment.objects.filter(stripe_checkout_session_id=session.get("id")).first()
            if payment:
                if session.get("status") in {"expired", "canceled"}:
                    payment.mark_canceled()
                else:
                    payment.mark_failed()
                if payment.enrollment_id:
                    Enrollment.objects.filter(id=payment.enrollment_id).update(payment_status="failed")
        except Exception:
            pass
        return Response({"success": False, "message": "Payment not completed."}, status=status.HTTP_400_BAD_REQUEST)

    success, message, context = _finalize_from_checkout_session(session)
    return Response({"success": True, "message": message, "data": context}, status=status.HTTP_200_OK)


@csrf_exempt
def stripe_webhook_view(request):
    """
    Stripe webhook to handle payment events (completed, failed, expired).
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            event = stripe.Event.construct_from(json.loads(payload.decode("utf-8") or "{}"), stripe.api_key)
    except Exception:
        return HttpResponse(status=400)

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        payment_id = obj.get("metadata", {}).get("payment_id")
        enrollment_id = obj.get("metadata", {}).get("enrollment_id")
        payment_intent_id = obj.get("payment_intent", "")
        customer_id = obj.get("customer", "")

        payment = Payment.objects.filter(id=payment_id).first() if payment_id else None
        if not payment:
            payment = Payment.objects.filter(stripe_checkout_session_id=obj.get("id")).first()
        if payment:
            payment.mark_succeeded(payment_intent_id, customer_id)

        if enrollment_id:
            enrollment = Enrollment.objects.filter(id=enrollment_id).first()
            if enrollment:
                enrollment.payment_status = "completed"
                enrollment.is_enrolled = True
                enrollment.save(update_fields=["payment_status", "is_enrolled", "updated_at"])
                enrollment.unlock_first_module()
                enrollment.calculate_progress()

    elif event_type in {"payment_intent.payment_failed"}:
        pi_id = obj.get("id", "")
        payment = Payment.objects.filter(stripe_payment_intent_id=pi_id).first()
        if payment:
            payment.mark_failed()
            if payment.enrollment_id:
                Enrollment.objects.filter(id=payment.enrollment_id).update(payment_status="failed")

    elif event_type in {"checkout.session.expired"}:
        payment = Payment.objects.filter(stripe_checkout_session_id=obj.get("id")).first()
        if payment:
            payment.mark_canceled()
            if payment.enrollment_id:
                Enrollment.objects.filter(id=payment.enrollment_id).update(payment_status="failed")

    return HttpResponse(status=200)
