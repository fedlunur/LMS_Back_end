from django.db.models.signals import post_save
from django.dispatch import receiver

from courses.models import Certificate
from courses.services.email_service import send_certificate_issued_email


@receiver(post_save, sender=Certificate)
def _certificate_issued_handler(sender, instance: Certificate, created: bool, **kwargs):
    if not created:
        return
    try:
        send_certificate_issued_email(instance)
    except Exception:
        # Non-blocking email
        pass


