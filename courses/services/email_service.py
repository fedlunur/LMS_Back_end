from typing import Optional, Tuple

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from courses.models import Enrollment, Certificate


def _common_context(enrollment: Enrollment) -> dict:
    student = enrollment.student
    course = enrollment.course
    return {
        "first_name": getattr(student, "first_name", "") or student.email,
        "full_name": student.get_full_name(),
        "email": student.email,
        "course_title": getattr(course, "title", ""),
        "course_price": getattr(course, "price", 0),
        "project_name": getattr(settings, "PROJECT_NAME", "Learning Management System"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
        "enrollment_id": enrollment.id,
    }


def _send(subject: str, to_email: str, txt_template: str, html_template: str, context: dict) -> None:
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)

    try:
        text_body = render_to_string(txt_template, context)
    except Exception:
        # Fallback plain text if txt template missing
        text_body = render_to_string(html_template, context)

    html_body = render_to_string(html_template, context)

    email_message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[to_email],
    )
    email_message.attach_alternative(html_body, "text/html")
    email_message.send()


def send_enrollment_email(enrollment: Enrollment, *, is_paid_pending: bool = False) -> None:
    """
    Notify user when they enroll in a course (free or paid).
    For paid/pending enrollments, the flavor informs that payment is required.
    """
    context = _common_context(enrollment)
    context.update({"is_paid_pending": is_paid_pending})

    if is_paid_pending:
        subject = getattr(
            settings,
            "ENROLLMENT_PENDING_EMAIL_SUBJECT",
            f"Enrollment started: {context['course_title']} (Payment required)",
        )
        txt_tmpl = "courses/emails/enrollment_pending.txt"
        html_tmpl = "courses/emails/enrollment_pending.html"
    else:
        subject = getattr(
            settings,
            "ENROLLMENT_CONFIRMED_EMAIL_SUBJECT",
            f"You're enrolled in {context['course_title']}",
        )
        txt_tmpl = "courses/emails/enrollment_confirmed.txt"
        html_tmpl = "courses/emails/enrollment_confirmed.html"

    _send(subject, context["email"], txt_tmpl, html_tmpl, context)


def send_payment_completed_email(enrollment: Enrollment) -> None:
    """Notify user when payment completes."""
    context = _common_context(enrollment)
    subject = getattr(
        settings,
        "PAYMENT_COMPLETED_EMAIL_SUBJECT",
        f"Payment received for {context['course_title']}",
    )
    _send(
        subject,
        context["email"],
        "courses/emails/payment_completed.txt",
        "courses/emails/payment_completed.html",
        context,
    )


def send_payment_failed_email(enrollment: Enrollment, *, reason: Optional[str] = None) -> None:
    """Notify user when payment fails."""
    context = _common_context(enrollment)
    context.update({"reason": reason})
    subject = getattr(
        settings,
        "PAYMENT_FAILED_EMAIL_SUBJECT",
        f"Payment failed for {context['course_title']}",
    )
    _send(
        subject,
        context["email"],
        "courses/emails/payment_failed.txt",
        "courses/emails/payment_failed.html",
        context,
    )


def send_course_completed_email(enrollment: Enrollment) -> None:
    """Notify user when they complete a course."""
    context = _common_context(enrollment)
    subject = getattr(
        settings,
        "COURSE_COMPLETED_EMAIL_SUBJECT",
        f"Congratulations! You completed {context['course_title']}",
    )
    _send(
        subject,
        context["email"],
        "courses/emails/course_completed.txt",
        "courses/emails/course_completed.html",
        context,
    )


def send_certificate_issued_email(certificate: Certificate) -> None:
    """Notify user when certificate is generated/issued."""
    enrollment = certificate.enrollment
    context = _common_context(enrollment)
    context.update(
        {
            "certificate_number": certificate.certificate_number,
            "issued_date": certificate.issued_date,
            "grade": certificate.grade,
        }
    )
    subject = getattr(
        settings,
        "CERTIFICATE_ISSUED_EMAIL_SUBJECT",
        f"Your certificate for {context['course_title']} is ready",
    )
    _send(
        subject,
        context["email"],
        "courses/emails/certificate_issued.txt",
        "courses/emails/certificate_issued.html",
        context,
    )


