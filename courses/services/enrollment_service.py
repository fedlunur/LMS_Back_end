from courses.models import Enrollment

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
        return True, "Payment completed successfully. Enrollment is now active."
    except Enrollment.DoesNotExist:
        return False, "Enrollment not found."
