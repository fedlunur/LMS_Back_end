import logging
import random
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from user_managment.models import PasswordResetToken, User
from lms_project.resend_email import send_email as send_resend_email

logger = logging.getLogger(__name__)

DEFAULT_EXPIRY_MINUTES = getattr(settings, "PASSWORD_RESET_TOKEN_EXPIRY_MINUTES", 15)
EMAIL_SUBJECT = getattr(settings, "PASSWORD_RESET_EMAIL_SUBJECT", "Reset your password")


def _generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def create_password_reset_token(user: User) -> PasswordResetToken:
    PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)

    code = _generate_code()
    expires_at = timezone.now() + timedelta(minutes=DEFAULT_EXPIRY_MINUTES)

    token = PasswordResetToken.objects.create(
        user=user,
        code=code,
        expires_at=expires_at,
    )
    return token


def _build_email_context(user: User, token: PasswordResetToken, extra_context: Optional[dict] = None) -> dict:
    context = {
        "first_name": user.first_name,
        "full_name": user.get_full_name(),
        "email": user.email,
        "code": token.code,
        "expires_minutes": DEFAULT_EXPIRY_MINUTES,
        "project_name": getattr(settings, "PROJECT_NAME", "Learning Management System"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
    }
    if extra_context:
        context.update(extra_context)
    return context


def send_password_reset_email(user: User, *, extra_context: Optional[dict] = None) -> PasswordResetToken:
    token = create_password_reset_token(user)

    context = _build_email_context(user, token, extra_context)

    try:
        success = send_resend_email(
            subject=EMAIL_SUBJECT,
            to_email=user.email,
            html_template="user_managment/emails/password_reset.html",
            txt_template="user_managment/emails/password_reset.txt",
            context=context,
        )
        
        if success:
            logger.info("Password reset code %s sent to %s via Resend", token.code, user.email)
        else:
            logger.error("Failed to send password reset email to %s via Resend", user.email)
            raise Exception("Failed to send email via Resend")
    except Exception:
        logger.exception("Failed to send password reset email to %s", user.email)
        raise

    return token
