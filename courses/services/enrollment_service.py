import logging
from courses.models import Enrollment

logger = logging.getLogger(__name__)

def enroll_user_in_course(user, course):
    """
    Handle user enrollment in a course.
    For free courses: enroll immediately with payment_status='completed'.
    For paid courses: require payment (future implementation), set payment_status='pending'.
    """
    if course.price > 0:
        # Future: Check payment status
        # For now, create enrollment with pending payment
        enrollment, created = Enrollment.objects.get_or_create(
            student=user,
            course=course,
            defaults={
                'progress': 0.0,
                'payment_status': 'pending',
                'is_enrolled': False
            }
        )
        if not created:
            return False, "Enrollment already exists."
        # Send enrollment pending email flavor
        try:
            from .email_service import send_enrollment_email
            send_enrollment_email(enrollment, is_paid_pending=True)
        except Exception as e:
            logger.error(f"Failed to send enrollment pending email for enrollment {enrollment.id}: {str(e)}", exc_info=True)
        return False, "Payment required for this course. Enrollment created with pending payment status."
    
    # Free course: enroll immediately
    if Enrollment.objects.filter(student=user, course=course).exists():
        return False, "Already enrolled in this course."
    
    enrollment = Enrollment.objects.create(
        student=user,
        course=course,
        progress=0.0,
        payment_status='completed',
        is_enrolled=True
    )
    enrollment.calculate_progress()
    # Unlock first module
    enrollment.unlock_first_module()
    # Send enrollment confirmed email flavor
    try:
        from .email_service import send_enrollment_email
        send_enrollment_email(enrollment, is_paid_pending=False)
    except Exception as e:
        logger.error(f"Failed to send enrollment confirmed email for enrollment {enrollment.id}: {str(e)}", exc_info=True)
    return True, "Successfully enrolled in the course."


def complete_payment(enrollment_id):
    """
    Mark payment as completed for an enrollment.
    This function can be called from payment webhooks or admin actions in the future.
    """
    try:
        enrollment = Enrollment.objects.get(id=enrollment_id)
        if enrollment.payment_status == 'completed':
            return False, "Payment already completed."
        
        enrollment.payment_status = 'completed'
        enrollment.is_enrolled = True
        enrollment.save(update_fields=['payment_status', 'is_enrolled'])
        # Unlock first module on activation
        enrollment.unlock_first_module()
        enrollment.calculate_progress()
        # Notify payment completion
        try:
            from .email_service import send_payment_completed_email
            send_payment_completed_email(enrollment)
        except Exception as e:
            logger.error(f"Failed to send payment completed email for enrollment {enrollment.id}: {str(e)}", exc_info=True)
        return True, "Payment completed successfully. Enrollment is now active."
    except Enrollment.DoesNotExist:
        return False, "Enrollment not found."


def fail_payment(enrollment_id, reason: str | None = None):
    """
    Mark payment as failed for an enrollment and notify the user.
    """
    try:
        enrollment = Enrollment.objects.get(id=enrollment_id)
        enrollment.payment_status = 'failed'
        enrollment.is_enrolled = False
        enrollment.save(update_fields=['payment_status', 'is_enrolled'])
        try:
            from .email_service import send_payment_failed_email
            send_payment_failed_email(enrollment, reason=reason)
        except Exception as e:
            logger.error(f"Failed to send payment failed email for enrollment {enrollment.id}: {str(e)}", exc_info=True)
        return True, "Payment marked as failed."
    except Enrollment.DoesNotExist:
        return False, "Enrollment not found."
