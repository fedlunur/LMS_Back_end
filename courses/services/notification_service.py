"""
Notification service for creating and managing user notifications.
"""
import logging
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from courses.models import Notification, NotificationType

logger = logging.getLogger(__name__)


def create_notification(
    user,
    notification_type,
    title,
    message,
    related_object=None,
    action_url=None,
    icon=None
):
    """
    Create a notification for a user.
    
    Args:
        user: User instance to receive the notification
        notification_type: NotificationType enum value
        title: Notification title
        message: Notification message/content
        related_object: Optional related object (enrollment, payment, etc.)
        action_url: Optional URL to navigate when clicked
        icon: Optional icon identifier
    
    Returns:
        Notification instance or None if creation failed
    """
    try:
        content_type = None
        object_id = None
        
        if related_object:
            content_type = ContentType.objects.get_for_model(related_object)
            object_id = related_object.id
        
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            content_type=content_type,
            object_id=object_id,
            action_url=action_url,
            icon=icon
        )
        return notification
    except Exception as e:
        logger.error(f"Failed to create notification for user {user.id}: {str(e)}", exc_info=True)
        return None


def send_enrollment_confirmed_notification(enrollment):
    """Send notification when enrollment is confirmed."""
    return create_notification(
        user=enrollment.student,
        notification_type=NotificationType.ENROLLMENT_CONFIRMED,
        title="Enrollment Confirmed",
        message=f"You have successfully enrolled in '{enrollment.course.title}'. Start learning now!",
        related_object=enrollment,
        action_url=f"/courses/{enrollment.course.id}",
        icon="enrollment"
    )


def send_enrollment_pending_notification(enrollment):
    """Send notification when enrollment is pending payment."""
    return create_notification(
        user=enrollment.student,
        notification_type=NotificationType.ENROLLMENT_PENDING,
        title="Payment Required",
        message=f"Your enrollment in '{enrollment.course.title}' is pending payment. Please complete the payment to access the course.",
        related_object=enrollment,
        action_url=f"/courses/{enrollment.course.id}/payment",
        icon="payment"
    )


def send_payment_completed_notification(enrollment):
    """Send notification when payment is completed."""
    return create_notification(
        user=enrollment.student,
        notification_type=NotificationType.PAYMENT_COMPLETED,
        title="Payment Completed",
        message=f"Your payment for '{enrollment.course.title}' has been completed. You can now access the course!",
        related_object=enrollment,
        action_url=f"/courses/{enrollment.course.id}",
        icon="payment"
    )


def send_payment_failed_notification(enrollment, reason=None):
    """Send notification when payment fails."""
    message = f"Your payment for '{enrollment.course.title}' has failed."
    if reason:
        message += f" Reason: {reason}"
    return create_notification(
        user=enrollment.student,
        notification_type=NotificationType.PAYMENT_FAILED,
        title="Payment Failed",
        message=message,
        related_object=enrollment,
        action_url=f"/courses/{enrollment.course.id}/payment",
        icon="payment"
    )


def send_course_completed_notification(enrollment):
    """Send notification when course is completed."""
    return create_notification(
        user=enrollment.student,
        notification_type=NotificationType.COURSE_COMPLETED,
        title="Course Completed!",
        message=f"Congratulations! You have completed '{enrollment.course.title}'. Great job!",
        related_object=enrollment,
        action_url=f"/courses/{enrollment.course.id}/certificate",
        icon="certificate"
    )


def send_certificate_issued_notification(certificate):
    """Send notification when certificate is issued."""
    return create_notification(
        user=certificate.enrollment.student,
        notification_type=NotificationType.CERTIFICATE_ISSUED,
        title="Certificate Issued",
        message=f"Your certificate for '{certificate.enrollment.course.title}' has been issued. Download it now!",
        related_object=certificate,
        action_url=f"/certificates/{certificate.id}",
        icon="certificate"
    )


def send_assignment_graded_notification(submission):
    """Send notification when assignment is graded."""
    return create_notification(
        user=submission.student,
        notification_type=NotificationType.ASSIGNMENT_GRADED,
        title="Assignment Graded",
        message=f"Your assignment '{submission.lesson.title}' has been graded. Score: {submission.score}/{submission.max_score}",
        related_object=submission,
        action_url=f"/lessons/{submission.lesson.id}/assignment",
        icon="assignment"
    )


def send_quiz_graded_notification(quiz_attempt):
    """Send notification when quiz is graded."""
    status = "passed" if quiz_attempt.passed else "failed"
    return create_notification(
        user=quiz_attempt.student,
        notification_type=NotificationType.QUIZ_GRADED,
        title="Quiz Graded",
        message=f"Your quiz '{quiz_attempt.lesson.title}' has been graded. You {status} with a score of {quiz_attempt.score}%.",
        related_object=quiz_attempt,
        action_url=f"/lessons/{quiz_attempt.lesson.id}/quiz",
        icon="quiz"
    )


def send_course_announcement_notification(announcement, enrolled_students):
    """
    Send notification for course announcement to enrolled students.
    
    Args:
        announcement: CourseAnnouncement instance
        enrolled_students: QuerySet or list of User instances
    """
    notifications = []
    for student in enrolled_students:
        notification = create_notification(
            user=student,
            notification_type=NotificationType.COURSE_ANNOUNCEMENT,
            title=f"New Announcement: {announcement.title}",
            message=announcement.content[:200] + "..." if len(announcement.content) > 200 else announcement.content,
            related_object=announcement,
            action_url=f"/courses/{announcement.course.id}/announcements",
            icon="announcement"
        )
        if notification:
            notifications.append(notification)
    return notifications


def send_lesson_unlocked_notification(enrollment, lesson):
    """Send notification when a lesson is unlocked."""
    return create_notification(
        user=enrollment.student,
        notification_type=NotificationType.LESSON_UNLOCKED,
        title="New Lesson Available",
        message=f"A new lesson '{lesson.title}' is now available in '{enrollment.course.title}'.",
        related_object=lesson,
        action_url=f"/lessons/{lesson.id}",
        icon="lesson"
    )


def send_module_unlocked_notification(enrollment, module):
    """Send notification when a module is unlocked."""
    return create_notification(
        user=enrollment.student,
        notification_type=NotificationType.MODULE_UNLOCKED,
        title="New Module Available",
        message=f"A new module '{module.title}' is now available in '{enrollment.course.title}'.",
        related_object=module,
        action_url=f"/courses/{enrollment.course.id}/modules/{module.id}",
        icon="module"
    )


def get_user_notifications(user, is_read=None, limit=None):
    """
    Get notifications for a user.
    
    Args:
        user: User instance
        is_read: Optional filter by read status (True/False)
        limit: Optional limit on number of notifications
    
    Returns:
        QuerySet of notifications
    """
    notifications = Notification.objects.filter(user=user)
    
    if is_read is not None:
        notifications = notifications.filter(is_read=is_read)
    
    if limit:
        notifications = notifications[:limit]
    
    return notifications


def mark_notification_as_read(notification_id, user):
    """
    Mark a notification as read.
    
    Args:
        notification_id: ID of the notification
        user: User instance (to ensure user can only mark their own notifications)
    
    Returns:
        Tuple (success: bool, message: str)
    """
    try:
        notification = Notification.objects.get(id=notification_id, user=user)
        notification.mark_as_read()
        return True, "Notification marked as read."
    except Notification.DoesNotExist:
        return False, "Notification not found."
    except Exception as e:
        logger.error(f"Failed to mark notification {notification_id} as read: {str(e)}", exc_info=True)
        return False, "Failed to mark notification as read."


def mark_all_notifications_as_read(user):
    """
    Mark all notifications as read for a user.
    
    Args:
        user: User instance
    
    Returns:
        Number of notifications marked as read
    """
    try:
        count = Notification.objects.filter(user=user, is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        return count
    except Exception as e:
        logger.error(f"Failed to mark all notifications as read for user {user.id}: {str(e)}", exc_info=True)
        return 0


def get_unread_notification_count(user):
    """Get count of unread notifications for a user."""
    return Notification.objects.filter(user=user, is_read=False).count()

