from django.utils import timezone
from django.db import transaction
from django.db.models import Q
import random

from ..models import (
    Enrollment, Lesson, AssignmentSubmission, AssignmentSubmissionFile,
    PeerReviewAssignment, PeerRubricEvaluation, PeerReviewSummary
)


def submit_assignment(user, lesson_id, submission_data, files=None):
    """
    Submit assignment for a lesson.
    submission_data: dict with 'submission_text', 'submission_file', 'submission_url', 'github_repo', 'code_snippet'
    files: list of uploaded files (max 5)
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
        
        # Validate file count
        if files and len(files) > assignment_lesson.max_files:
            return False, f"Maximum {assignment_lesson.max_files} files allowed.", None
        
        submitted_at = timezone.now()
        
        with transaction.atomic():
            # Determine initial status based on peer review setting
            initial_status = 'submitted'
            if assignment_lesson.peer_review_enabled:
                initial_status = 'pending_peer_review'
            
            # Create submission
            submission = AssignmentSubmission.objects.create(
                student=user,
                lesson=lesson,
                enrollment=enrollment,
                submission_text=submission_data.get('submission_text', ''),
                submission_file=submission_data.get('submission_file'),
                submission_url=submission_data.get('submission_url', ''),
                github_repo=submission_data.get('github_repo', ''),
                code_snippet=submission_data.get('code_snippet', ''),
                status=initial_status,
                submitted_at=submitted_at,
                attempt_number=existing_submissions + 1,
                max_score=assignment_lesson.max_score
            )
            
            # Handle multiple file uploads
            if files:
                for file in files[:assignment_lesson.max_files]:
                    AssignmentSubmissionFile.objects.create(
                        submission=submission,
                        file=file,
                        original_filename=file.name
                    )
            
            # If peer review is enabled, assign a peer reviewer
            if assignment_lesson.peer_review_enabled:
                assign_peer_reviewer(submission)
        
        return True, "Assignment submitted successfully.", submission
    
    except Lesson.DoesNotExist:
        return False, "Lesson not found.", None
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course.", None


def assign_peer_reviewer(submission):
    """
    Assign a peer reviewer to a submission and assign this student to review someone else.
    Each student reviews only one other student's submission.
    """
    lesson = submission.lesson
    student = submission.student
    
    # First, assign this student to review someone else's submission
    assign_student_as_reviewer(student, lesson)
    
    # Then, find someone to review this submission
    find_reviewer_for_submission(submission)


def find_reviewer_for_submission(submission):
    """
    Find a reviewer for this submission from students who have submitted but not yet assigned to review.
    """
    lesson = submission.lesson
    student = submission.student
    
    # Check if this submission already has a reviewer
    if PeerReviewAssignment.objects.filter(submission=submission).exists():
        return
    
    # Get all students who have submitted (excluding the submission owner)
    submitted_students = AssignmentSubmission.objects.filter(
        lesson=lesson,
        status__in=['submitted', 'pending_peer_review', 'peer_reviewed', 'graded']
    ).exclude(student=student).values_list('student_id', flat=True).distinct()
    
    # Get students who are already assigned to review something for this lesson
    already_assigned_reviewers = PeerReviewAssignment.objects.filter(
        lesson=lesson
    ).values_list('reviewer_id', flat=True)
    
    # Find potential reviewers (submitted but not yet assigned to review anyone)
    potential_reviewers = list(set(submitted_students) - set(already_assigned_reviewers))
    
    if potential_reviewers:
        reviewer_id = random.choice(potential_reviewers)
        PeerReviewAssignment.objects.create(
            submission=submission,
            reviewer_id=reviewer_id,
            lesson=lesson
        )


def assign_student_as_reviewer(student, lesson):
    """
    Assign the student to review another submission if they haven't been assigned yet.
    """
    # Check if student already has a review assignment for this lesson
    existing_assignment = PeerReviewAssignment.objects.filter(
        reviewer=student,
        lesson=lesson
    ).exists()
    
    if existing_assignment:
        return
    
    # Find submissions that need a reviewer (excluding student's own)
    # Priority: submissions without any reviewer first
    submissions_without_reviewer = AssignmentSubmission.objects.filter(
        lesson=lesson,
        status__in=['pending_peer_review']
    ).exclude(student=student).exclude(
        peer_review_assignments__isnull=False
    )
    
    if submissions_without_reviewer.exists():
        # Randomly select one to review
        submission_to_review = random.choice(list(submissions_without_reviewer))
        PeerReviewAssignment.objects.create(
            submission=submission_to_review,
            reviewer=student,
            lesson=lesson
        )
        return
    
    # If all submissions have reviewers, find any submission not by this student
    # that this student hasn't been assigned to review yet
    all_other_submissions = AssignmentSubmission.objects.filter(
        lesson=lesson,
        status__in=['pending_peer_review', 'peer_reviewed']
    ).exclude(student=student)
    
    for sub in all_other_submissions:
        # Check if this student is not already reviewing this submission
        if not PeerReviewAssignment.objects.filter(submission=sub, reviewer=student).exists():
            PeerReviewAssignment.objects.create(
                submission=sub,
                reviewer=student,
                lesson=lesson
            )
            return


def rebalance_peer_reviews(lesson):
    """
    Called periodically or on-demand to ensure all submissions have reviewers
    and all submitted students have something to review.
    """
    assignment_lesson = getattr(lesson, 'assignment', None)
    if not assignment_lesson or not assignment_lesson.peer_review_enabled:
        return
    
    # Get all submissions pending peer review
    pending_submissions = AssignmentSubmission.objects.filter(
        lesson=lesson,
        status='pending_peer_review'
    )
    
    for submission in pending_submissions:
        # Ensure each submission has a reviewer
        if not PeerReviewAssignment.objects.filter(submission=submission).exists():
            find_reviewer_for_submission(submission)
    
    # Ensure each student who submitted has something to review
    submitted_students = AssignmentSubmission.objects.filter(
        lesson=lesson,
        status__in=['submitted', 'pending_peer_review', 'peer_reviewed', 'graded']
    ).values_list('student', flat=True).distinct()
    
    for student_id in submitted_students:
        from user_managment.models import User
        try:
            student = User.objects.get(id=student_id)
            assign_student_as_reviewer(student, lesson)
        except User.DoesNotExist:
            pass


def get_peer_review_assignment(user, lesson_id):
    """
    Get the peer review assignment for a student.
    Returns the submission they need to review (anonymized).
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        
        # Check if peer review is enabled for this assignment
        assignment_lesson = getattr(lesson, 'assignment', None)
        if not assignment_lesson or not assignment_lesson.peer_review_enabled:
            return None, "Peer review is not enabled for this assignment."
        
        # Check if student has submitted their own assignment first
        has_submitted = AssignmentSubmission.objects.filter(
            student=user,
            lesson=lesson,
            status__in=['submitted', 'pending_peer_review', 'peer_reviewed', 'graded']
        ).exists()
        
        if not has_submitted:
            return None, "You must submit your assignment before reviewing others."
        
        # Get their peer review assignment
        assignment = PeerReviewAssignment.objects.filter(
            reviewer=user,
            lesson=lesson,
            is_completed=False
        ).select_related('submission').first()
        
        # If no assignment found, try to assign one now
        if not assignment:
            assign_student_as_reviewer(user, lesson)
            # Try again
            assignment = PeerReviewAssignment.objects.filter(
                reviewer=user,
                lesson=lesson,
                is_completed=False
            ).select_related('submission').first()
        
        if not assignment:
            # Check if there are any other submissions to review
            other_submissions = AssignmentSubmission.objects.filter(
                lesson=lesson,
                status__in=['pending_peer_review', 'peer_reviewed']
            ).exclude(student=user).count()
            
            if other_submissions == 0:
                return None, "No other submissions available for peer review yet. Please check back later."
            else:
                return None, "All available submissions have been assigned for review. Please check back later."
        
        # Return anonymized submission data
        submission = assignment.submission
        
        # Get files with full URL
        files_data = []
        for f in submission.files.all():
            files_data.append({
                'id': f.id,
                'file': f.file.url if f.file else None,
                'original_filename': f.original_filename,
                'file_size': f.file_size
            })
        
        # Also include the legacy single file if exists
        legacy_file = None
        if submission.submission_file:
            legacy_file = {
                'url': submission.submission_file.url,
                'name': submission.submission_file.name
            }
        
        return {
            'peer_review_id': assignment.id,
            'submission_text': submission.submission_text,
            'submission_url': submission.submission_url,
            'github_repo': submission.github_repo,
            'code_snippet': submission.code_snippet,
            'submission_file': legacy_file,
            # 'files': files_data,
            'rubric_criteria': assignment_lesson.rubric_criteria,
        }, None
    
    except Lesson.DoesNotExist:
        return None, "Lesson not found."


def submit_peer_review(user, peer_review_id, evaluations):
    """
    Submit peer review evaluation.
    evaluations: list of dicts with 'criterion_name', 'points_awarded', 'feedback'
    """
    try:
        peer_review = PeerReviewAssignment.objects.get(
            id=peer_review_id,
            reviewer=user,
            is_completed=False
        )
        
        with transaction.atomic():
            total_points = 0
            max_points = 0
            
            for eval_data in evaluations:
                evaluation = PeerRubricEvaluation.objects.create(
                    peer_review=peer_review,
                    criterion_name=eval_data.get('criterion_name', ''),
                    criterion_description=eval_data.get('criterion_description', ''),
                    max_points=eval_data.get('max_points', 10),
                    points_awarded=eval_data.get('points_awarded', 0),
                    feedback=eval_data.get('feedback', '')
                )
                total_points += evaluation.points_awarded
                max_points += evaluation.max_points
            
            # Mark peer review as completed
            peer_review.is_completed = True
            peer_review.completed_at = timezone.now()
            peer_review.save()
            
            # Update submission status
            submission = peer_review.submission
            submission.status = 'peer_reviewed'
            submission.save()
            
            # Create or update peer review summary
            summary, created = PeerReviewSummary.objects.get_or_create(
                submission=submission,
                defaults={
                    'total_rubric_score': total_points,
                    'max_rubric_score': max_points,
                    'reviewed_at': timezone.now()
                }
            )
            if not created:
                summary.total_rubric_score = total_points
                summary.max_rubric_score = max_points
                summary.reviewed_at = timezone.now()
                summary.save()
        
        return True, "Peer review submitted successfully."
    
    except PeerReviewAssignment.DoesNotExist:
        return False, "Peer review assignment not found or already completed."


def grade_assignment(teacher, submission_id, score, feedback):
    """
    Teacher grades an assignment submission.
    """
    try:
        submission = AssignmentSubmission.objects.select_related(
            'lesson__assignment', 'lesson__course'
        ).get(id=submission_id)
        
        # Verify teacher owns the course
        if submission.lesson.course.instructor != teacher:
            return False, "You are not authorized to grade this submission.", None
        
        submission.score = score
        submission.feedback = feedback
        submission.graded_by = teacher
        submission.graded_at = timezone.now()
        submission.status = 'graded'
        submission.save()
        
        return True, "Assignment graded successfully.", submission
    
    except AssignmentSubmission.DoesNotExist:
        return False, "Submission not found.", None


def get_submission_with_peer_review(teacher, submission_id):
    """
    Get submission details including peer review scores (for teacher view).
    """
    try:
        submission = AssignmentSubmission.objects.select_related(
            'lesson__assignment', 'student', 'peer_review_summary'
        ).prefetch_related('files').get(id=submission_id)
        
        # Verify teacher owns the course
        if submission.lesson.course.instructor != teacher:
            return None, "Not authorized."
        
        peer_review_data = None
        if hasattr(submission, 'peer_review_summary'):
            summary = submission.peer_review_summary
            # Get detailed rubric evaluations
            peer_review = PeerReviewAssignment.objects.filter(
                submission=submission,
                is_completed=True
            ).first()
            
            evaluations = []
            if peer_review:
                evaluations = list(peer_review.rubric_evaluations.values(
                    'criterion_name', 'max_points', 'points_awarded', 'feedback'
                ))
            
            peer_review_data = {
                'total_score': summary.total_rubric_score,
                'max_score': summary.max_rubric_score,
                'percentage': (summary.total_rubric_score / summary.max_rubric_score * 100) if summary.max_rubric_score > 0 else 0,
                'reviewed_at': summary.reviewed_at,
                'evaluations': evaluations
            }
        
        return {
            'submission': submission,
            'peer_review': peer_review_data,
            'is_late': submission.is_late,
            'late_deduction': submission.late_deduction_applied,
            'files': list(submission.files.values('id', 'file', 'original_filename', 'file_size'))
        }, None
    
    except AssignmentSubmission.DoesNotExist:
        return None, "Submission not found."


def get_all_submissions_for_lesson(teacher, lesson_id):
    """
    Get all submissions for a lesson with peer review summaries (for teacher).
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        
        if lesson.course.instructor != teacher:
            return None, "Not authorized."
        
        submissions = AssignmentSubmission.objects.filter(
            lesson=lesson
        ).select_related('student', 'peer_review_summary').prefetch_related('files')
        
        result = []
        for sub in submissions:
            peer_score = None
            if hasattr(sub, 'peer_review_summary'):
                summary = sub.peer_review_summary
                peer_score = {
                    'score': summary.total_rubric_score,
                    'max': summary.max_rubric_score
                }
            
            result.append({
                'id': sub.id,
                'student_name': sub.student.get_full_name() or sub.student.email,
                'student_email': sub.student.email,
                'status': sub.status,
                'submitted_at': sub.submitted_at,
                'is_late': sub.is_late,
                'late_deduction': sub.late_deduction_applied,
                'score': sub.score,
                'final_score': sub.final_score,
                'peer_review_score': peer_score,
                'file_count': sub.files.count()
            })
        
        return result, None
    
    except Lesson.DoesNotExist:
        return None, "Lesson not found."
