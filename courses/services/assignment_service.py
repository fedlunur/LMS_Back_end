from django.utils import timezone
from ..models import Enrollment, Lesson, AssignmentSubmission


def submit_assignment(user, lesson_id, submission_data):
    """
    Submit assignment for a lesson.
    submission_data: dict with 'submission_text', 'submission_file', 'submission_url', 'github_repo'
    Returns: (success, message, submission)
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)
        
        if enrollment.payment_status != 'completed':
            return False, "Payment not completed for this course.", None
        
        if lesson.content_type != Lesson.ContentType.ASSIGNMENT:
            return False, "This lesson is not an assignment.", None
        
        assignment_lesson = getattr(lesson, 'assignment', None)
        if not assignment_lesson:
            return False, "Assignment configuration not found.", None
        
        # Check attempt number
        existing_submissions = AssignmentSubmission.objects.filter(
            student=user,
            lesson=lesson
        ).count()
        
        max_attempts = assignment_lesson.max_attempts
        if existing_submissions >= max_attempts:
            return False, f"Maximum attempts ({max_attempts}) reached for this assignment.", None
        
        # Create submission
        submission = AssignmentSubmission.objects.create(
            student=user,
            lesson=lesson,
            enrollment=enrollment,
            submission_text=submission_data.get('submission_text', ''),
            submission_file=submission_data.get('submission_file'),
            submission_url=submission_data.get('submission_url', ''),
            github_repo=submission_data.get('github_repo', ''),
            status='submitted',
            submitted_at=timezone.now(),
            attempt_number=existing_submissions + 1,
            max_score=assignment_lesson.max_score
        )
        
        return True, "Assignment submitted successfully.", submission
    
    except Lesson.DoesNotExist:
        return False, "Lesson not found.", None
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course.", None
